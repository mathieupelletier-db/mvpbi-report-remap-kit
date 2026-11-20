-- Line-item grain metric view, as produced by Genie Code /importBI from Model A, plus o_orderkey exposed as a
-- dimension so Order Count and Avg Order Value can be published to Power BI.
CREATE OR REPLACE VIEW {{target}}.mv_lineitem
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1

source: {{source}}.lineitem

joins:
  - name: orders
    source: {{source}}.orders
    "on": source.l_orderkey = orders.o_orderkey
    joins:
      - name: customer
        source: {{source}}.customer
        "on": orders.o_custkey = customer.c_custkey
        joins:
          - name: nation
            source: {{source}}.nation
            "on": customer.c_nationkey = nation.n_nationkey
            joins:
              - name: region
                source: {{source}}.region
                "on": nation.n_regionkey = region.r_regionkey

comment: Line item sales metrics migrated from the Power BI model (TPC-H)

dimensions:
  - name: l_orderkey
    expr: l_orderkey

  - name: l_linenumber
    expr: l_linenumber

  - name: l_partkey
    expr: l_partkey

  - name: l_suppkey
    expr: l_suppkey

  - name: l_quantity
    expr: l_quantity

  - name: l_extendedprice
    expr: l_extendedprice

  - name: l_discount
    expr: l_discount

  - name: l_tax
    expr: l_tax

  - name: l_returnflag
    expr: l_returnflag

  - name: l_linestatus
    expr: l_linestatus

  - name: l_shipdate
    expr: l_shipdate

  - name: l_commitdate
    expr: l_commitdate

  - name: l_receiptdate
    expr: l_receiptdate

  - name: l_shipinstruct
    expr: l_shipinstruct

  - name: l_shipmode
    expr: l_shipmode

  - name: o_custkey
    expr: orders.o_custkey

  - name: o_orderstatus
    expr: orders.o_orderstatus

  - name: o_totalprice
    expr: orders.o_totalprice

  - name: o_orderdate
    expr: orders.o_orderdate

  - name: o_orderpriority
    expr: orders.o_orderpriority

  - name: o_clerk
    expr: orders.o_clerk

  - name: o_shippriority
    expr: orders.o_shippriority

  - name: c_name
    expr: orders.customer.c_name

  - name: c_mktsegment
    expr: orders.customer.c_mktsegment

  - name: c_acctbal
    expr: orders.customer.c_acctbal

  - name: c_nationkey
    expr: orders.customer.c_nationkey

  - name: n_name
    expr: orders.customer.nation.n_name

  - name: n_regionkey
    expr: orders.customer.nation.n_regionkey

  - name: r_name
    expr: orders.customer.nation.region.r_name

  - name: o_orderkey
    expr: orders.o_orderkey
    comment: Measure input for Order Count (Power BI computes measures from exposed columns)

measures:
  - name: Total Revenue
    expr: SUM(l_extendedprice * (1 - l_discount))
    format:
      type: currency
      currency_code: USD
      decimal_places:
        type: exact
        places: 2

  - name: Line Item Count
    expr: COUNT(1)
    format:
      type: number
      decimal_places:
        type: exact
        places: 0

  - name: Order Count
    expr: COUNT(DISTINCT orders.o_orderkey)
    format:
      type: number
      decimal_places:
        type: exact
        places: 0

  - name: Avg Order Value
    expr: "try_divide(MEASURE(`Total Revenue`), MEASURE(`Order Count`))"
    format:
      type: currency
      currency_code: USD
      decimal_places:
        type: exact
        places: 2
$$;
