"""Check everything the kit needs before creating anything. Read-only."""
from _common import Client, load, sql
from mvpbi_remap.fabric import FABRIC, PBI, PBI_RES

cfg = load()
ok = True


def check(name, fn):
    global ok
    try:
        print(f"  ok    {name}: {fn()}")
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"  FAIL  {name}: {str(e)[:300]}")


print("Databricks")
check("SQL warehouse answers", lambda: sql(cfg, "SELECT current_user()")[0][0])
check(f"source tables in {cfg.source}", lambda: ", ".join(r[1] for r in sql(cfg, f"SHOW TABLES IN {cfg.source}")))
check(f"target catalog {cfg.target_catalog} visible", lambda: sql(cfg, f"DESCRIBE CATALOG {cfg.target_catalog}") and "yes")
print("Power BI")
c = Client(cfg.workspace_id)
check("az login token for Fabric", lambda: bool(c._token("https://api.fabric.microsoft.com")) and "yes")
ws = {}
check("workspace reachable", lambda: ws.update(c.req("GET", f"{FABRIC}/workspaces/{cfg.workspace_id}").json()) or ws.get("displayName") or ws)
check("workspace on a capacity", lambda: ws.get("capacityId") or (_ for _ in ()).throw(RuntimeError("no capacity: Premium, PPU or Fabric capacity needed")))
check("Power BI API reachable", lambda: c.req("GET", f"{PBI}/groups/{cfg.workspace_id}/datasets", res=PBI_RES).status_code)
print()
print("Not checkable by API, confirm manually:")
print(f"  - Databricks workspace Previews page (https://{cfg.host}/previews): 'Publish Metric View To Powerbi' is ON")
print("  - Power BI capacity setting: XMLA endpoint = Read Write")
raise SystemExit(0 if ok else 1)
