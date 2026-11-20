"""Rewrite a Power BI report (PBIR) so its visuals point at fields of a different semantic model.

A PBIR visual references fields as (Entity, Property) pairs inside semantic-query JSON:

    {"Column":  {"Expression": {"SourceRef": {"Entity": "nation"}}, "Property": "n_name"}}
    {"Measure": {"Expression": {"SourceRef": {"Entity": "lineitem"}}, "Property": "Total Revenue"}}
    {"Aggregation": {"Expression": {"Column": ...}, "Function": 5}}        # implicit measure

Filters use aliases instead: {"From": [{"Name": "o", "Entity": "orders"}]} plus
{"SourceRef": {"Source": "o"}}. Selectors and sorts repeat the field as a
"queryRef" string ("lineitem.Total Revenue"). All of these have to move together,
or Power BI shows "Something's wrong with one or more fields".

The mapping is a list of rules, each {"from": {...}, "to": {...}} where a side is
{"entity", "property", "kind"} with kind in Column | Measure | Aggregation (plus
"function" for Aggregation). An Aggregation rule lets an implicit aggregation of a
dimension column be replaced by an explicit measure, which matters when the target
model is flattened to a different grain (COUNT of a customer column over a
lineitem-grain table is no longer a customer count).
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field

# Power BI semantic-query aggregate enum (2 = "Count (Distinct)" in the UI, 5 = plain "Count").
AGG_NAMES = {0: "Sum", 1: "Avg", 2: "Count", 3: "Min", 4: "Max", 5: "CountNonNull"}
# Labels Power BI shows for an implicit measure with no displayName ("Count of c_custkey").
# 5 -> "Count" verified on a rendered report; the others follow Power BI's UI wording.
AGG_UI = {0: "Sum", 1: "Average", 2: "Count (Distinct)", 3: "Minimum", 4: "Maximum", 5: "Count"}


@dataclass(frozen=True)
class Ref:
    entity: str
    property: str
    kind: str                 # Column | Measure | Aggregation
    function: int | None = None


@dataclass
class Mapping:
    """Candidate targets per source field, in preference order.

    A source field can map to several tables (nation[n_name] exists in both
    mv_lineitem and mv_customer). Published metric views have no relationships
    between them, so every visual must be served by ONE table: the rewriter picks,
    per visual, the first table (in `preference` order) that has a target for
    every field the visual uses.
    """
    rules: dict[Ref, list[Ref]] = field(default_factory=dict)
    preference: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Mapping":
        rules: dict[Ref, list[Ref]] = {}
        pref: list[str] = list(d.get("target_tables", []))
        for r in d["fields"]:
            f, t = r["from"], r["to"]
            tgt = Ref(t["entity"], t["property"], t["kind"], t.get("function"))
            rules.setdefault(Ref(f["entity"], f["property"], f["kind"], f.get("function")), []).append(tgt)
            if tgt.entity not in pref:
                pref.append(tgt.entity)
        return cls(rules, pref)

    def candidates(self, ref: Ref) -> list[Ref]:
        c = list(self.rules.get(ref, []))
        if ref.kind == "Aggregation":
            # Implicit aggregation of a column that maps to a column: keep the aggregation.
            c += [Ref(x.entity, x.property, "Aggregation", ref.function)
                  for x in self.rules.get(Ref(ref.entity, ref.property, "Column"), [])]
        return c

    def pick_table(self, refs: list[Ref]) -> str | None:
        if not refs:
            return None
        common = set.intersection(*({x.entity for x in self.candidates(r)} for r in refs))
        for t in self.preference:
            if t in common:
                return t
        return None

    def lookup(self, ref: Ref, table: str | None) -> Ref | None:
        return next((x for x in self.candidates(ref) if x.entity == table), None)


@dataclass
class VisualResult:
    path: str
    mapped: list[tuple[str, str]] = field(default_factory=list)
    unmapped: list[str] = field(default_factory=list)
    table: str | None = None
    is_filter_source: bool = False   # slicer or page filter: filters other visuals

    @property
    def ok(self) -> bool:
        return not self.unmapped


def query_ref(ref: Ref) -> str:
    base = f"{ref.entity}.{ref.property}"
    if ref.kind == "Aggregation":
        return f"{AGG_NAMES.get(ref.function, str(ref.function))}({base})"
    return base


def _label(qref: str) -> str:
    """'lineitem.Total Revenue' -> 'Total Revenue'; 'Sum(t.amount)' -> 'amount'."""
    inner = qref[qref.index("(") + 1:-1] if qref.endswith(")") and "(" in qref else qref
    return inner.split(".", 1)[1] if "." in inner else inner


def _field_node(ref: Ref, alias: str | None = None) -> dict:
    src = {"Source": alias} if alias else {"Entity": ref.entity}
    if ref.kind == "Measure":
        return {"Measure": {"Expression": {"SourceRef": src}, "Property": ref.property}}
    col = {"Column": {"Expression": {"SourceRef": src}, "Property": ref.property}}
    if ref.kind == "Aggregation":
        return {"Aggregation": {"Expression": col, "Function": ref.function}}
    return col


def _ref_of(fnode: dict) -> Ref | None:
    """Ref for a field node that uses Entity (not alias) source refs."""
    if "Aggregation" in fnode:
        c = fnode["Aggregation"]["Expression"]["Column"]
        return Ref(c["Expression"]["SourceRef"].get("Entity"), c["Property"], "Aggregation",
                   fnode["Aggregation"]["Function"])
    for kind in ("Column", "Measure"):
        if kind in fnode:
            return Ref(fnode[kind]["Expression"]["SourceRef"].get("Entity"), fnode[kind]["Property"], kind)
    return None


def _src_entity(src: dict, aliases: dict[str, str]) -> tuple[str | None, str | None]:
    """Return (entity, alias) for a SourceRef, resolving filter aliases."""
    if "Entity" in src:
        return src["Entity"], None
    alias = src.get("Source")
    return aliases.get(alias), alias


class Rewriter:
    def __init__(self, mapping: Mapping, target_entity_for_alias: str | None = None) -> None:
        self.m = mapping
        self.qref: dict[str, str] = {}          # old queryRef -> new queryRef
        self.result: VisualResult | None = None
        # Filters' "From" aliases are re-pointed at whatever entity their fields map to.
        self.alias_target: dict[str, str] = {}

    # -- field-level --------------------------------------------------------
    def _map_ref(self, ref: Ref, alias: str | None) -> dict | None:
        tgt = self.m.lookup(ref, self.table)
        if tgt is None:
            self.result.unmapped.append(query_ref(ref))
            return None
        if alias:
            self.alias_target[alias] = tgt.entity
        self.qref[query_ref(ref)] = query_ref(tgt)
        self.result.mapped.append((query_ref(ref), query_ref(tgt)))
        if alias and tgt.kind == ref.kind:
            return _field_node(tgt, alias)
        return _field_node(tgt)

    def _try_field(self, node: dict, aliases: dict[str, str]) -> dict | None:
        """If node is a field expression, return its rewritten form (or the node if unmappable)."""
        if "Aggregation" in node and "Column" in node["Aggregation"].get("Expression", {}):
            inner = node["Aggregation"]["Expression"]["Column"]
            ent, alias = _src_entity(inner["Expression"]["SourceRef"], aliases)
            ref = Ref(ent, inner["Property"], "Aggregation", node["Aggregation"]["Function"])
            return self._map_ref(ref, alias) or node
        for kind in ("Column", "Measure"):
            if kind in node and isinstance(node[kind], dict) and "Property" in node[kind]:
                ent, alias = _src_entity(node[kind]["Expression"]["SourceRef"], aliases)
                return self._map_ref(Ref(ent, node[kind]["Property"], kind), alias) or node
        return None

    # -- tree walk ----------------------------------------------------------
    def _walk(self, node, aliases: dict[str, str]):
        if isinstance(node, list):
            return [self._walk(x, aliases) for x in node]
        if not isinstance(node, dict):
            return node
        if "From" in node and isinstance(node["From"], list):
            aliases = {**aliases, **{f["Name"]: f["Entity"] for f in node["From"] if "Entity" in f}}
        rewritten = self._try_field(node, aliases)
        if rewritten is not None:
            return rewritten
        out = {k: self._walk(v, aliases) for k, v in node.items()}
        if "field" in node and "queryRef" in node and out["field"] != node["field"]:
            # A projection: its queryRef must follow the field, whatever form the old one had.
            new_ref, old_ref = _ref_of(out["field"]), _ref_of(node["field"])
            if new_ref is not None:
                self.qref[node["queryRef"]] = query_ref(new_ref)
            if old_ref is not None and "displayName" not in node:
                # Keep the label Power BI showed for the original field.
                out["displayName"] = (f"{AGG_UI.get(old_ref.function, 'Value')} of {old_ref.property}"
                                      if old_ref.kind == "Aggregation" else old_ref.property)
        if "From" in out and isinstance(out["From"], list):
            for f in out["From"]:
                if f.get("Name") in self.alias_target:
                    f["Entity"] = self.alias_target[f["Name"]]
        return out

    def _fix_strings(self, node, renames: dict[str, str]):
        """Second pass: queryRef / selector metadata strings that echo old field names."""
        if isinstance(node, list):
            return [self._fix_strings(x, renames) for x in node]
        if isinstance(node, dict):
            out = {}
            for k, v in node.items():
                if k in ("queryRef", "metadata") and isinstance(v, str) and v in self.qref:
                    out[k] = self.qref[v]
                else:
                    out[k] = self._fix_strings(v, renames)
            return out
        return node

    def _keep_labels(self, visual: dict) -> None:
        """Projections whose field was renamed keep their on-screen label via displayName."""
        qs = visual.get("visual", {}).get("query", {}).get("queryState", {})
        for role in qs.values():
            for p in role.get("projections", []):
                old = p.get("queryRef")
                if old not in self.qref:
                    continue
                p.setdefault("displayName", _label(old))
                p["queryRef"] = self.qref[old]
                p["nativeQueryRef"] = _label(self.qref[old])

    def _collect(self, node, aliases, out: list[Ref]) -> None:
        if isinstance(node, list):
            for x in node:
                self._collect(x, aliases, out)
            return
        if not isinstance(node, dict):
            return
        if "From" in node and isinstance(node["From"], list):
            aliases = {**aliases, **{f["Name"]: f["Entity"] for f in node["From"] if "Entity" in f}}
        if "Aggregation" in node and "Column" in node["Aggregation"].get("Expression", {}):
            c = node["Aggregation"]["Expression"]["Column"]
            out.append(Ref(_src_entity(c["Expression"]["SourceRef"], aliases)[0], c["Property"],
                           "Aggregation", node["Aggregation"]["Function"]))
            return
        for kind in ("Column", "Measure"):
            if kind in node and isinstance(node[kind], dict) and "Property" in node[kind]:
                out.append(Ref(_src_entity(node[kind]["Expression"]["SourceRef"], aliases)[0],
                               node[kind]["Property"], kind))
                return
        for v in node.values():
            self._collect(v, aliases, out)

    def rewrite_json(self, path: str, doc: dict) -> tuple[dict, VisualResult]:
        self.result = VisualResult(path)
        self.qref, self.alias_target = {}, {}
        refs: list[Ref] = []
        self._collect(doc, {}, refs)
        self.table = self.m.pick_table(refs)
        self.result.table = self.table
        self.result.is_filter_source = (path.endswith("page.json")
                                        or doc.get("visual", {}).get("visualType") == "slicer")
        if refs and self.table is None:
            # No single published table serves every field: leave the visual untouched.
            per = {query_ref(r): sorted({x.entity for x in self.m.candidates(r)}) for r in refs}
            self.result.unmapped = [f"{k} -> {v or 'no target'}" for k, v in per.items()]
            return copy.deepcopy(doc), self.result
        new = self._walk(copy.deepcopy(doc), {})
        self._keep_labels(new)
        new = self._fix_strings(new, self.qref)
        return new, self.result


def rewrite_report(parts: dict[str, bytes], mapping: Mapping, target_model_id: str
                   ) -> tuple[dict[str, bytes], list[VisualResult]]:
    """Rewrite every visual/page/report JSON part and repoint definition.pbir."""
    rw = Rewriter(mapping)
    out, results = {}, []
    for path, data in parts.items():
        if path == "definition.pbir":
            pbir = json.loads(data)
            pbir["datasetReference"] = {"byConnection": {
                "connectionString": f"semanticmodelid={target_model_id}"}}
            out[path] = json.dumps(pbir, indent=2).encode()
        elif path.endswith(("visual.json", "page.json", "report.json")):
            doc, res = rw.rewrite_json(path, json.loads(data))
            out[path] = json.dumps(doc, indent=2).encode()
            if res.mapped or res.unmapped:
                results.append(res)
        else:
            out[path] = data
    return out, results


def scope_warnings(results: list[VisualResult]) -> list[str]:
    """Slicers and page filters only reach visuals on the same published table."""
    warns = []
    pages: dict[str, list[VisualResult]] = {}
    for r in results:
        if "/pages/" in r.path:
            pages.setdefault(r.path.split("/pages/")[1].split("/")[0], []).append(r)
    for page, rs in pages.items():
        for src in (r for r in rs if r.is_filter_source and r.table):
            for v in rs:
                if v is not src and not v.path.endswith("page.json") and v.table and v.table != src.table:
                    who = "page filter" if src.path.endswith("page.json") else src.path.split("/visuals/")[1].split("/")[0]
                    warns.append(f"{page}: {who} ({src.table}) no longer filters "
                                 f"{v.path.split('/visuals/')[1].split('/')[0]} ({v.table})")
    return warns
