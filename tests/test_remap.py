import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mvpbi_remap.remap import Mapping, Rewriter, rewrite_report  # noqa: E402

MV = "orders_mv"
MAPPING = Mapping.from_dict({"fields": [
    {"from": {"entity": "lineitem", "property": "Total Revenue", "kind": "Measure"},
     "to": {"entity": MV, "property": "total_revenue", "kind": "Measure"}},
    {"from": {"entity": "nation", "property": "n_name", "kind": "Column"},
     "to": {"entity": MV, "property": "customer_nation", "kind": "Column"}},
    {"from": {"entity": "orders", "property": "o_orderpriority", "kind": "Column"},
     "to": {"entity": MV, "property": "order_priority", "kind": "Column"}},
    {"from": {"entity": "region", "property": "r_name", "kind": "Column"},
     "to": {"entity": MV, "property": "customer_region", "kind": "Column"}},
    {"from": {"entity": "orders", "property": "o_orderdate", "kind": "Column"},
     "to": {"entity": MV, "property": "order_date", "kind": "Column"}},
    {"from": {"entity": "customer", "property": "c_custkey", "kind": "Aggregation", "function": 5},
     "to": {"entity": MV, "property": "customer_count", "kind": "Measure"}},
]})
DEMO = ROOT / "templates" / "report_a" / "definition" / "pages"


def load(rel):
    return json.loads((DEMO / rel).read_text())


def refs(doc):
    """All (Entity-or-Source, Property) pairs left in a document."""
    out = []

    def walk(n):
        if isinstance(n, dict):
            for k in ("Column", "Measure"):
                if k in n and isinstance(n[k], dict) and "Property" in n[k]:
                    out.append((k, n[k]["Expression"]["SourceRef"], n[k]["Property"]))
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)
    walk(doc)
    return out


def test_measure_and_column_projection_rewritten_with_label_kept():
    new, res = Rewriter(MAPPING).rewrite_json("x", load("page1/visuals/bar_revenue_nation/visual.json"))
    assert res.ok, res.unmapped
    assert all(src.get("Entity") == MV for _, src, _ in refs(new))
    projs = [p for r in new["visual"]["query"]["queryState"].values() for p in r["projections"]]
    assert {p["queryRef"] for p in projs} == {f"{MV}.customer_nation", f"{MV}.total_revenue"}
    assert {p["displayName"] for p in projs} == {"n_name", "Total Revenue"}


def test_implicit_aggregation_becomes_explicit_measure():
    new, res = Rewriter(MAPPING).rewrite_json("x", load("scalable/visuals/card_customers/visual.json"))
    proj = new["visual"]["query"]["queryState"]["Values"]["projections"][0]
    assert proj["field"] == {"Measure": {"Expression": {"SourceRef": {"Entity": MV}}, "Property": "customer_count"}}
    assert proj["displayName"] == "# Customers"          # original label survives
    assert proj["queryRef"] == f"{MV}.customer_count"


def test_filter_aliases_and_sort_rewritten():
    new, res = Rewriter(MAPPING).rewrite_json("x", load("trend/visuals/line_revenue_date/visual.json"))
    assert res.ok, res.unmapped
    f = new["filterConfig"]["filters"][0]
    assert f["filter"]["From"][0]["Entity"] == MV
    cond = f["filter"]["Where"][0]["Condition"]["In"]["Expressions"][0]["Column"]
    assert cond == {"Expression": {"SourceRef": {"Source": "o"}}, "Property": "order_priority"}
    sort = new["visual"]["query"]["sortDefinition"]["sort"][0]["field"]["Column"]["Property"]
    assert sort == "order_date"


def test_page_filter_rewritten():
    new, res = Rewriter(MAPPING).rewrite_json("x", load("trend/page.json"))
    assert res.ok
    assert new["filterConfig"]["filters"][0]["filter"]["From"][0]["Entity"] == MV


def test_unmapped_fields_are_reported_not_dropped():
    new, res = Rewriter(Mapping()).rewrite_json("x", load("page1/visuals/card_orders/visual.json"))
    assert res.unmapped == ["orders.Order Count -> no target"]
    assert new == load("page1/visuals/card_orders/visual.json")


def test_rewrite_report_repoints_pbir():
    parts = {"definition.pbir": json.dumps({"version": "4.0", "datasetReference": {"byConnection": {
        "connectionString": "semanticmodelid=OLD"}}}).encode()}
    out, _ = rewrite_report(parts, MAPPING, "NEW")
    assert json.loads(out["definition.pbir"])["datasetReference"]["byConnection"]["connectionString"] \
        == "semanticmodelid=NEW"


def test_parity_dax_for_filtered_line_chart():
    from mvpbi_remap.parity import visual_dax
    dax = visual_dax(load("trend/visuals/line_revenue_date/visual.json"), load("trend/page.json"))
    assert dax == ("EVALUATE SUMMARIZECOLUMNS('orders'[o_orderdate], "
                   "TREATAS({\"1-URGENT\", \"2-HIGH\"}, 'orders'[o_orderpriority]), "
                   "TREATAS({\"AMERICA\", \"EUROPE\"}, 'region'[r_name]), "
                   "\"m0\", CALCULATE([Total Revenue]))")


def test_parity_dax_for_slicer_and_implicit_count():
    from mvpbi_remap.parity import visual_dax
    assert visual_dax(load("simple/visuals/slicer_priority/visual.json")) == \
        "EVALUATE VALUES('orders'[o_orderpriority])"
    assert visual_dax(load("scalable/visuals/card_customers/visual.json")) == \
        "EVALUATE SUMMARIZECOLUMNS(\"m0\", COUNTA('customer'[c_custkey]))"


def test_visual_goes_to_the_one_table_that_serves_all_its_fields():
    m = Mapping.from_dict({"target_tables": ["mv_lineitem", "mv_customer"], "fields": [
        {"from": {"entity": "nation", "property": "n_name", "kind": "Column"},
         "to": {"entity": "mv_lineitem", "property": "n_name", "kind": "Column"}},
        {"from": {"entity": "nation", "property": "n_name", "kind": "Column"},
         "to": {"entity": "mv_customer", "property": "n_name", "kind": "Column"}},
        {"from": {"entity": "customer", "property": "c_custkey", "kind": "Aggregation", "function": 5},
         "to": {"entity": "mv_customer", "property": "Customer Count", "kind": "Measure"}},
        {"from": {"entity": "orders", "property": "Avg Order Value", "kind": "Measure"},
         "to": {"entity": "mv_lineitem", "property": "Avg Order Value", "kind": "Measure"}}]})
    new, res = Rewriter(m).rewrite_json("x", load("scalable/visuals/bar_customers_nation/visual.json"))
    assert res.table == "mv_customer" and res.ok
    # Avg Order Value (mv_lineitem only) + customer count (mv_customer only): no single table.
    new, res = Rewriter(m).rewrite_json("x", load("trend/visuals/table_top_nations/visual.json"))
    assert res.table is None and not res.ok
    assert new == load("trend/visuals/table_top_nations/visual.json")


def test_scope_warning_when_slicer_and_visual_land_on_different_tables():
    from mvpbi_remap.remap import VisualResult, scope_warnings
    rs = [VisualResult("definition/pages/p/visuals/slicer/visual.json", table="mv_lineitem", is_filter_source=True),
          VisualResult("definition/pages/p/visuals/card/visual.json", table="mv_customer")]
    assert scope_warnings(rs) == ["p: slicer (mv_lineitem) no longer filters card (mv_customer)"]


def test_converted_implicit_measure_keeps_power_bi_default_label():
    m = Mapping.from_dict({"fields": [
        {"from": {"entity": "customer", "property": "c_custkey", "kind": "Aggregation", "function": 5},
         "to": {"entity": "mv_customer", "property": "Customer Count", "kind": "Measure"}},
        {"from": {"entity": "region", "property": "r_name", "kind": "Column"},
         "to": {"entity": "mv_customer", "property": "r_name", "kind": "Column"}},
        {"from": {"entity": "nation", "property": "n_name", "kind": "Column"},
         "to": {"entity": "mv_customer", "property": "n_name", "kind": "Column"}}]})
    new, res = Rewriter(m).rewrite_json("x", load("scalable/visuals/table_by_nation/visual.json"))
    labels = [p.get("displayName") for p in new["visual"]["query"]["queryState"]["Values"]["projections"]]
    assert labels == ["r_name", "n_name", "Count of c_custkey"]
