"""Delete what the kit created: Power BI items named <prefix>* plus the published model, and the two metric views.

Lists everything first and asks for confirmation (or pass --yes).
"""
import sys

from _common import Client, load, sql
from mvpbi_remap.fabric import FABRIC

cfg = load()
c = Client(cfg.workspace_id)
items = [i for i in c.items() if i["displayName"].startswith(cfg.prefix)
         or (i["type"] == "SemanticModel" and i["displayName"] == cfg.model_b)]
views = [f"{cfg.target}.{v}" for v in ("mv_lineitem", "mv_customer")]
print("Power BI items to delete:", [(i["type"], i["displayName"]) for i in items] or "none")
print("Metric views to drop:", views)
if "--yes" not in sys.argv and input("Delete these? [y/N] ").strip().lower() != "y":
    raise SystemExit("nothing deleted")
for i in items:
    r = c.req("DELETE", f"{FABRIC}/workspaces/{cfg.workspace_id}/items/{i['id']}")
    print("deleted", i["type"], i["displayName"], r.status_code)
for v in views:
    sql(cfg, f"DROP VIEW IF EXISTS {v}")
    print("dropped", v)
print(f"The schema {cfg.target} was left in place (drop it yourself if the kit created it).")
