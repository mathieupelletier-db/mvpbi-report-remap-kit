"""Propose a field mapping from Model A (star schema) to Model B (published metric view).

Columns are matched on lineage, not on names: each metric view dimension whose
expression is a plain column reference (`source.col` or `<join>.col`, nested joins
allowed) resolves to a (UC table, column) pair, and so does every Model A column
(partition source table + sourceColumn). Measures are matched on a normalized
name ("Total Revenue" ~ "total_revenue"), then must be reviewed: a name match is a
suggestion, the parity check is the proof.
"""
from __future__ import annotations

import re

import yaml


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def model_a_fields(tmdl_tables: dict[str, str]) -> tuple[dict, dict]:
    """From TMDL table files -> ({(table, col): (uc_table, source_col)}, {measure: table})."""
    cols, measures = {}, {}
    for tname, txt in tmdl_tables.items():
        uc = re.search(r'tbl = sch\{\[Name="([^"]+)"\]\}', txt)
        uc_table = uc.group(1) if uc else tname
        for m in re.finditer(r"^\tcolumn (\S+)\n(?:\t\t.*\n)*?\t\tsourceColumn: (\S+)", txt, re.M):
            cols[(tname, m.group(1).strip("'"))] = (uc_table, m.group(2))
        for m in re.finditer(r"^\tmeasure '?([^'=]+?)'? =", txt, re.M):
            measures[m.group(1).strip()] = tname
    return cols, measures


def mv_fields(yaml_text: str) -> tuple[dict, list[str], str]:
    """From metric view YAML -> ({(uc_table, col): dim_name}, [measure names], source table)."""
    d = yaml.safe_load(yaml_text)
    src = d["source"].split(".")[-1]
    alias_table = {"source": src}

    def walk(joins, parent):
        for j in joins or []:
            alias_table[j["name"]] = j["source"].split(".")[-1]
            walk(j.get("joins"), j["name"])
    walk(d.get("joins"), "source")
    dims = {}
    for f in d.get("dimensions", d.get("fields", [])):
        expr = f["expr"].strip()
        if not re.fullmatch(r"`?[A-Za-z_]\w*`?(\.`?[A-Za-z_]\w*`?)*", expr):
            continue                       # computed dimension: no single-column lineage
        path = [x.strip("`") for x in expr.split(".")]
        name = f.get("name") or path[-1]   # YAML 1.1 derives the name from the expression
        table = alias_table.get(path[-2]) if len(path) > 1 else src
        if table:
            dims.setdefault((table, path[-1]), name)
    return dims, [m["name"] for m in d.get("measures", [])], src


def suggest(tmdl_tables: dict[str, str], mv_yaml: str, mv_table: str) -> dict:
    a_cols, a_meas = model_a_fields(tmdl_tables)
    b_dims, b_meas, _ = mv_fields(mv_yaml)
    fields, unmatched = [], []
    for (t, c), lineage in sorted(a_cols.items()):
        if lineage in b_dims:
            fields.append({"from": {"entity": t, "property": c, "kind": "Column"},
                           "to": {"entity": mv_table, "property": b_dims[lineage], "kind": "Column"},
                           "basis": f"lineage {lineage[0]}.{lineage[1]}"})
        else:
            unmatched.append(f"column {t}.{c}")
    by_norm = {norm(m): m for m in b_meas}
    for m, t in sorted(a_meas.items()):
        if norm(m) in by_norm:
            fields.append({"from": {"entity": t, "property": m, "kind": "Measure"},
                           "to": {"entity": mv_table, "property": by_norm[norm(m)], "kind": "Measure"},
                           "basis": "normalized name"})
        else:
            unmatched.append(f"measure {t}.{m}")
    return {"target_entity": mv_table, "fields": fields, "unmatched": unmatched}
