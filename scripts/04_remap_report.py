"""Rewrite Report A's visuals onto Model B (the published metric views) and push the result.

  --in-place   update Report A itself (same report id and URL), now bound to Model B
  default      create a new report <prefix>report_b next to it
  --dry-run    rewrite and report only
Writes out/report_b/ (rewritten PBIR) and out/remap.md.
"""
import argparse
import json

from _common import OUT, ROOT, Client, load
from mvpbi_remap.remap import Mapping, rewrite_report, scope_warnings

cfg = load()
ap = argparse.ArgumentParser()
ap.add_argument("--mapping", default=str(ROOT / "mapping" / "mapping.json"))
ap.add_argument("--in-place", action="store_true")
ap.add_argument("--dry-run", action="store_true")
a = ap.parse_args()

c = Client(cfg.workspace_id)
report = c.find(cfg.report_a, "Report")
model_b = c.find(cfg.model_b, "SemanticModel")
if not model_b:
    raise SystemExit(f"Semantic model '{cfg.model_b}' not found: publish the metric views first (docs/publish.md).")
parts = {k: v for k, v in c.get_definition(report["id"]).items() if k != ".platform"}
(OUT / "report_a").mkdir(parents=True, exist_ok=True)
for k, v in parts.items():                                   # keep the original for the parity check
    f = OUT / "report_a" / k; f.parent.mkdir(parents=True, exist_ok=True); f.write_bytes(v)
new_parts, results = rewrite_report(parts, Mapping.from_dict(json.loads(open(a.mapping).read())), model_b["id"])
for k, v in new_parts.items():
    f = OUT / "report_b" / k; f.parent.mkdir(parents=True, exist_ok=True); f.write_bytes(v)

rows = ["| part | target table | fields remapped | not remapped |", "|---|---|---|---|"]
for r in sorted(results, key=lambda r: r.path):
    name = r.path.replace("definition/pages/", "").replace("/visual.json", "").replace("/visuals/", " / ")
    rows.append(f"| {name} | {r.table or '-'} | {len(r.mapped)} | {'; '.join(r.unmapped) or '-'} |")
bad = [r for r in results if not r.ok]
warns = scope_warnings(results)
summary = f"{len(results) - len(bad)}/{len(results)} parts fully remapped"
(OUT / "remap.md").write_text(f"# Remap result\n\n{summary}\n\n" + "\n".join(rows) + "\n\n## Filter scope warnings\n\n"
                              + ("\n".join(f"- {w}" for w in warns) or "None") + "\n")
print(summary)
for w in warns:
    print("  SCOPE", w)
for r in bad:
    print("  NOT REMAPPED", r.path, r.unmapped)
if a.dry_run:
    raise SystemExit(0)
if a.in_place:
    c.update_definition(report["id"], new_parts)
    rid = report["id"]
    print("updated in place:", cfg.report_a, rid)
else:
    name = cfg.prefix + "report_b"
    ex = c.find(name, "Report")
    if ex:
        c.update_definition(ex["id"], new_parts); rid = ex["id"]
    else:
        c.create(name, "Report", new_parts); rid = c.find(name, "Report")["id"]
    print("report:", name, rid)
bound = c.report(rid).get("datasetId")
print("bound to:", bound, "(Model B)" if bound == model_b["id"] else f"!= Model B {model_b['id']}")
