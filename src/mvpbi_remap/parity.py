"""Numeric parity: the same visual, queried through Model A and through Model B, must return the same rows.

For each visual we build the DAX that the visual effectively asks for:
SUMMARIZECOLUMNS(<group-by columns>, <visual + page filters as TREATAS>, "m0", <measure>, ...).
The rewritten visual (pointing at Model B) produces a query of the same shape, so
rows can be compared position by position after sorting on the group-by values.

Covers the field shapes used in this demo (Column, Measure, Aggregation, Categorical
In filters). Anything else raises, so an unsupported visual is never silently passed.
"""
from __future__ import annotations

import math

# Power BI semantic-query aggregate enum -> DAX. Note: 2 is "Count (Distinct)" in the UI,
# 5 is plain "Count" (non-blank values).
AGG_DAX = {0: "SUM", 1: "AVERAGE", 2: "DISTINCTCOUNT", 3: "MIN", 4: "MAX", 5: "COUNTA"}
GROUP_ROLES = ("Category", "Rows", "Series", "Columns", "Legend", "Axis")


def _q(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def _col(entity: str, prop: str) -> str:
    return f"{_q(entity)}[{prop}]"


def _expr(field: dict, aliases: dict[str, str] | None = None) -> tuple[str, str]:
    """Return (kind, dax) for a field node; kind is 'group' or 'value'."""
    aliases = aliases or {}

    def ent(src):
        return src["Entity"] if "Entity" in src else aliases[src["Source"]]
    if "Column" in field:
        c = field["Column"]
        return "group", _col(ent(c["Expression"]["SourceRef"]), c["Property"])
    if "Measure" in field:
        m = field["Measure"]
        return "value", f"CALCULATE([{m['Property']}])"
    if "Aggregation" in field:
        a = field["Aggregation"]
        c = a["Expression"]["Column"]
        return "value", f"{AGG_DAX[a['Function']]}({_col(ent(c['Expression']['SourceRef']), c['Property'])})"
    raise ValueError(f"unsupported field: {field}")


def _lit(v: str) -> str:
    """Power BI literal ('text', 12L, 3.5D) -> DAX literal."""
    if v.startswith("'") and v.endswith("'"):
        return '"' + v[1:-1].replace("''", "'").replace('"', '""') + '"'
    return v.rstrip("LDM")


def _filters(filter_config: dict | None) -> list[str]:
    out = []
    for f in (filter_config or {}).get("filters", []):
        flt = f.get("filter")
        if not flt:
            continue
        aliases = {x["Name"]: x["Entity"] for x in flt.get("From", [])}
        for w in flt.get("Where", []):
            cond = w["Condition"]
            if "In" not in cond:
                raise ValueError(f"unsupported filter condition: {list(cond)}")
            _, col = _expr(cond["In"]["Expressions"][0], aliases)
            vals = ", ".join(_lit(v[0]["Literal"]["Value"]) for v in cond["In"]["Values"])
            out.append(f"TREATAS({{{vals}}}, {col})")
    return out


def visual_dax(visual: dict, page: dict | None = None) -> str | None:
    """DAX equivalent of a visual's query; None for visuals with no data fields."""
    v = visual.get("visual", {})
    qs = v.get("query", {}).get("queryState", {})
    groups, values = [], []
    for role, spec in qs.items():
        for p in spec.get("projections", []):
            kind, dax = _expr(p["field"])
            (groups if kind == "group" else values).append(dax)
    if not groups and not values:
        return None
    filters = _filters(visual.get("filterConfig")) + _filters((page or {}).get("filterConfig"))
    if not values:  # slicer: distinct values of its column under the filters
        if filters:
            return f"EVALUATE CALCULATETABLE(VALUES({groups[0]}), {', '.join(filters)})"
        return f"EVALUATE VALUES({groups[0]})"
    args = groups + filters + [f'"m{i}", {d}' for i, d in enumerate(values)]
    return "EVALUATE SUMMARIZECOLUMNS(" + ", ".join(args) + ")"


def _norm(row: dict) -> tuple:
    return tuple(row.values())


def is_blank_member(row: dict) -> bool:
    return all(v is None for v in row.values())


def compare(rows_a: list[dict], rows_b: list[dict], rel_tol: float = 1e-9) -> list[str]:
    """Return a list of differences (empty when equal)."""
    a = sorted((_norm(r) for r in rows_a), key=lambda t: tuple(str(x) for x in t))
    b = sorted((_norm(r) for r in rows_b), key=lambda t: tuple(str(x) for x in t))
    if len(a) != len(b):
        return [f"row count {len(a)} vs {len(b)}"]
    diffs = []
    for ra, rb in zip(a, b):
        for x, y in zip(ra, rb):
            same = (math.isclose(x, y, rel_tol=rel_tol, abs_tol=1e-9)
                    if isinstance(x, (int, float)) and isinstance(y, (int, float)) else x == y)
            if not same:
                diffs.append(f"{ra} vs {rb}")
                break
        if len(diffs) >= 5:
            diffs.append("...")
            break
    return diffs
