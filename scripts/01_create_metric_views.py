"""Create the target schema and the metric views over the TPC-H source tables."""
from _common import ROOT, load, sql

cfg = load()
sql(cfg, f"CREATE SCHEMA IF NOT EXISTS {cfg.target}")
for name in ("mv_lineitem", "mv_customer"):
    ddl = cfg.render((ROOT / "templates/metric_views" / f"{name}.sql").read_text())
    sql(cfg, "\n".join(l for l in ddl.splitlines() if not l.startswith("--")))
    print("created", f"{cfg.target}.{name}")
rev, orders, lines = sql(cfg, f"SELECT MEASURE(`Total Revenue`), MEASURE(`Order Count`), MEASURE(`Line Item Count`) "
                              f"FROM {cfg.target}.mv_lineitem")[0]
cust = sql(cfg, f"SELECT MEASURE(`Customer Count`) FROM {cfg.target}.mv_customer")[0][0]
print(f"smoke test: revenue {float(rev):,.2f} | orders {int(orders):,} | line items {int(lines):,} | customers {int(cust):,}")
