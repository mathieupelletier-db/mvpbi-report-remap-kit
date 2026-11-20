-- Customer-grain metric view. Report A counts customers with an implicit COUNT over customer[c_custkey],
-- which includes customers who never ordered. That count does not exist at line-item grain, so it gets
-- its own metric view. c_custkey stays a dimension so each row is one customer (Power BI's COUNT(1)
-- translation counts distinct dimension combinations).
CREATE OR REPLACE VIEW {{target}}.mv_customer
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: Customer counts at customer grain, including customers with no orders
source: {{source}}.customer
joins:
  - name: nation
    source: {{source}}.nation
    "on": source.c_nationkey = nation.n_nationkey
    joins:
      - name: region
        source: {{source}}.region
        "on": nation.n_regionkey = region.r_regionkey
dimensions:
  - name: c_custkey
    expr: c_custkey
  - name: c_name
    expr: c_name
  - name: n_name
    expr: nation.n_name
  - name: r_name
    expr: nation.region.r_name
measures:
  - name: Customer Count
    expr: COUNT(1)
$$;
