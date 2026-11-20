"""For every visual: the same DAX through Model A (original fields) and Model B (remapped fields); compare.

Run after 04_remap_report.py (reads out/report_a and out/report_b). Writes out/parity.md and out/parity.json.
"""
import json
import time

from _common import OUT, Client, load
from mvpbi_remap.parity import compare, is_blank_member, visual_dax

cfg = load()
c = Client(cfg.workspace_id)
ma = c.find(cfg.model_a, "SemanticModel")["id"]
mb = c.find(cfg.model_b, "SemanticModel")["id"]
A, B = OUT / "report_a" / "definition" / "pages", OUT / "report_b" / "definition" / "pages"
rows, out = ["| visual | rows | Model A (s) | Model B (s) | result |", "|---|---|---|---|---|"], []
for va in sorted(A.glob("*/visuals/*/visual.json")):
    rel = va.relative_to(A); vb = B / rel; page = rel.parts[0]
    rec = {"visual": f"{page}/{rel.parts[2]}"}
    if json.loads(va.read_text()) == json.loads(vb.read_text()):
        rec.update(result="NOT REMAPPED", note="left unchanged (no single published table serves its fields)")
    else:
        dax_a = visual_dax(json.loads(va.read_text()), json.loads((A / page / "page.json").read_text()))
        dax_b = visual_dax(json.loads(vb.read_text()), json.loads((B / page / "page.json").read_text()))
        try:
            t = time.time(); ra = c.dax(ma, dax_a); rec["sec_a"] = round(time.time() - t, 1)
            t = time.time(); rb = c.dax(mb, dax_b); rec["sec_b"] = round(time.time() - t, 1)
            diffs = compare(ra, rb)
            rec.update(rows=len(ra), result="MATCH" if not diffs else "DIFF", diffs=diffs)
            if diffs and any(is_blank_member(r) for r in ra) and not compare([r for r in ra if not is_blank_member(r)], rb):
                rec.update(result="MATCH", diffs=[], note="Model A also lists a virtual (Blank) member")
        except Exception as e:  # noqa: BLE001
            rec.update(result="ERROR", note=str(e)[:300])
    out.append(rec)
    note = rec.get("note") or "; ".join(rec.get("diffs", []))[:160]
    rows.append(f"| {rec['visual']} | {rec.get('rows', '-')} | {rec.get('sec_a', '-')} | {rec.get('sec_b', '-')} | "
                f"{rec['result']}{(': ' + note) if note else ''} |")
    print(rows[-1])
ok = sum(r["result"] == "MATCH" for r in out)
remapped = sum(r["result"] != "NOT REMAPPED" for r in out)
(OUT / "parity.json").write_text(json.dumps(out, indent=2))
(OUT / "parity.md").write_text(f"# Parity: Model A vs Model B\n\n{ok}/{remapped} remapped visuals return identical rows.\n\n"
                               + "\n".join(rows) + "\n")
print(f"{ok}/{remapped} remapped visuals MATCH; {len(out) - remapped} not remapped")
raise SystemExit(0 if ok == remapped else 1)
