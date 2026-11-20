"""Propose mapping/mapping.suggested.json from Model A's TMDL and the live metric view definitions.

Columns are matched on lineage (source table + column), measures on normalized name. Compare with the
reviewed mapping/mapping.json (which also carries the one manual rule: Report A's implicit customer count
-> the governed Customer Count measure) and adjust if your metric views differ.
"""
import json
import re

from _common import ROOT, load, sql, template_parts
from mvpbi_remap.suggest import suggest

cfg = load()
tables = {k.split("/")[-1][:-5]: v.decode() for k, v in template_parts("model_a", cfg).items()
          if k.startswith("definition/tables/")}
views = ["mv_lineitem", "mv_customer"]
out = {"target_tables": views, "fields": [], "unmatched": []}
sets = []
for v in views:
    ddl = sql(cfg, f"SHOW CREATE TABLE {cfg.target}.{v}")[0][0]
    s = suggest(tables, ddl.split("$$")[1], v)
    out["fields"] += s["fields"]
    sets.append(set(s["unmatched"]))
    print(f"{v}: {len(s['fields'])} fields matched")
out["unmatched"] = sorted(set.intersection(*sets))
(ROOT / "mapping" / "mapping.suggested.json").write_text(json.dumps(out, indent=2) + "\n")
print("wrote mapping/mapping.suggested.json; not matched in any view:", out["unmatched"])
