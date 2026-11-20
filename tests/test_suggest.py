import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mvpbi_remap.suggest import suggest  # noqa: E402

YAML = """
version: 1.1
source: samples.tpch.lineitem
joins:
  - name: orders
    source: samples.tpch.orders
    "on": source.l_orderkey = orders.o_orderkey
    joins:
      - name: customer
        source: samples.tpch.customer
        "on": orders.o_custkey = customer.c_custkey
        joins:
          - name: nation
            source: samples.tpch.nation
            "on": customer.c_nationkey = nation.n_nationkey
dimensions:
  - name: order_priority
    expr: orders.o_orderpriority
  - name: customer_nation
    expr: nation.n_name
  - name: l_discount
    expr: source.l_discount
measures:
  - name: total_revenue
    expr: SUM(source.l_extendedprice * (1 - source.l_discount))
"""


def tables():
    d = ROOT / "templates" / "model_a" / "definition" / "tables"
    return {p.stem: p.read_text().replace("{{source_catalog}}", "samples").replace("{{source_schema}}", "tpch")
            for p in d.glob("*.tmdl")}


def test_columns_match_on_lineage_and_measures_on_name():
    s = suggest(tables(), YAML, "mv")
    got = {(f["from"]["entity"], f["from"]["property"]): f["to"]["property"] for f in s["fields"]}
    assert got[("orders", "o_orderpriority")] == "order_priority"
    assert got[("nation", "n_name")] == "customer_nation"       # 3 joins deep
    assert got[("lineitem", "l_discount")] == "l_discount"
    assert got[("lineitem", "Total Revenue")] == "total_revenue"
    assert "measure orders.Order Count" in s["unmatched"]
