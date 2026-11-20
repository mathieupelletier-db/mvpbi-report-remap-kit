"""Shared setup for the numbered scripts: config, Power BI client, SQL via the Databricks CLI."""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mvpbi_remap.config import load, template_parts  # noqa: E402,F401
from mvpbi_remap.fabric import Client  # noqa: E402,F401

OUT = ROOT / "out"


def sql(cfg, statement: str, wait: str = "50s") -> list:
    """Run one SQL statement on the configured warehouse; return data rows (raises on failure)."""
    body = {"warehouse_id": cfg.warehouse_id, "statement": statement, "wait_timeout": wait}
    r = subprocess.run(["databricks", "api", "post", "/api/2.0/sql/statements", "--profile", cfg.profile,
                        "--json", json.dumps(body)], capture_output=True, text=True)
    if not r.stdout.strip().startswith("{"):
        raise RuntimeError(f"Databricks CLI failed (profile {cfg.profile}): {r.stderr.strip()[:300]}")
    d = json.loads(r.stdout)
    st = d.get("status", {})
    if st.get("state") != "SUCCEEDED":
        raise RuntimeError(f"SQL {st.get('state')}: {st.get('error', {}).get('message', '')[:400]}")
    return d.get("result", {}).get("data_array", []) or []
