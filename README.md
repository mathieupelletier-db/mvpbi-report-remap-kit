# Repoint a Power BI report onto Unity Catalog metric views

You moved a Power BI semantic model's business logic into **Unity Catalog metric views** (for example with
Genie Code `/importBI`) and published them back to Power BI with **Publish to Power BI**. The existing report
still points at the old semantic model, and rebinding it breaks every visual: a published metric view is one
table named after the view, with the metric view's field names, while the report asks for the old tables and
names (`nation[n_name]`, `lineitem[Total Revenue]`).

This kit **rewrites the report's own field references** (visuals, filters, sorts, slicers, implicit measures),
pushes it back **bound to the published metric views with the same report ID and URL**, and then **proves every
visual returns the same rows** through both models. It runs end to end on the TPC-H sample data that ships
with every Unity Catalog workspace (`samples.tpch`), so you can try it before pointing it at your own reports.

> Provided as-is under the [DB License](LICENSE.md); Databricks does not offer official support for it
> (see [NOTICE.md](NOTICE.md)). Publishing metric views to Power BI is a **Private Preview** feature: your
> workspace must be enrolled (ask your Databricks account team) and the preview switched on by a workspace admin.

https://github.com/user-attachments/assets/49f631f9-ece3-4c89-9ed3-75aca71b0b02

*Recorded on a TPC-H SF10 copy; the kit defaults to `samples.tpch`, so your numbers will differ. Subtitles: [video/…narrated.srt](video/mvpbi-report-remap-walkthrough-narrated.srt).*

## What you get

| | |
|---|---|
| Model A + Report A | A star-schema Power BI semantic model over TPC-H (8 tables, 7 relationships, 4 DAX measures, DirectQuery on Databricks SQL) and a 5-page, 17-visual report with visual and page filters, sorts and slicers |
| Metric views | `mv_lineitem` (line-item grain, the 4 measures) and `mv_customer` (customer grain), ready to publish |
| Remap | Rewrites Report A onto the published semantic model (Model B), in place or as a new report |
| Proof | A per-visual DAX parity check between Model A and Model B, plus a remap report listing anything that could not be moved |

## Prerequisites

- **Databricks:** a Unity Catalog workspace with the *Publish Metric View To Powerbi* preview on
  (Settings → Previews), a SQL warehouse, `CREATE SCHEMA` on a catalog of your choice, and the
  [Databricks CLI](https://docs.databricks.com/dev-tools/cli/) signed in (`databricks auth login --profile <name>`).
- **Power BI:** a workspace on Premium, Premium Per User or Fabric capacity, with the XMLA endpoint set to
  *Read Write*, where you are Contributor or higher; and the [Azure CLI](https://learn.microsoft.com/cli/azure/)
  signed in to the same Microsoft Entra tenant (`az login`).
- **Local:** Python 3.10+ and `pip install -r requirements.txt`.

No secrets are stored: SQL runs through your Databricks CLI profile, and Power BI calls use your `az login` session.

## Quickstart

```bash
cp config.example.yaml config.yaml      # fill in workspace host, warehouse, target schema, Power BI workspace
cd scripts
python3 00_preflight.py                 # read-only checks
python3 01_create_metric_views.py       # metric views over samples.tpch in your target schema
python3 02_deploy_powerbi.py            # Model A + Report A in your Power BI workspace
#   -> manual: publish the two metric views to Power BI (docs/publish.md, ~2 minutes)
python3 03_suggest_mapping.py           # optional: regenerate the field mapping from your live metric views
python3 04_remap_report.py --dry-run    # see what will change
python3 04_remap_report.py --in-place   # repoint Report A itself (or omit --in-place to create Report B)
python3 05_parity_check.py              # same DAX per visual through both models
```

If `02_deploy_powerbi.py` reports that Model A cannot query Databricks, set its data source credentials once
(docs/publish.md, step 0) and run it again.

## Expected result

On TPC-H the remap rewrites **17 of 18 report parts**, and **all 16 remapped visuals return identical rows**
through Model B. The remaining visual and three slicer interactions are reported, not silently changed:

- **Visuals that combine two facts.** Each published metric view becomes its own Power BI table, with no
  relationships between them, so a visual can only use one of them. `trend / table_top_nations` needs
  Avg Order Value (`mv_lineitem`) and a customer count (`mv_customer`), so it is left as is and listed.
- **Slicers and page filters** only reach visuals on their own table. `out/remap.md` lists each case.
- **Grain changes hide in implicit measures.** Report A counts `customer[c_custkey]`, which includes customers
  who never ordered. At line-item grain that count would silently change, which is why there is a separate
  customer-grain metric view, and why columns are matched on lineage rather than on names.
- Model A's slicers list a virtual "(Blank)" member that Power BI adds for DirectQuery relationships;
  Model B has none. The parity check treats this as a match and says so.

## How it works

1. `src/mvpbi_remap/remap.py` walks the report definition (PBIR) and rewrites every field reference using a
   mapping (`mapping/mapping.json`): projections, filters with aliases, sort definitions, selector strings and
   implicit aggregations. For each visual it picks the one published table that can serve all its fields.
   Labels are kept, including Power BI's default label for implicit measures ("Count of c_custkey").
2. `04_remap_report.py` pushes the rewritten definition with the Fabric REST API `updateDefinition` call,
   together with a new dataset reference. Power BI keeps the report's ID and URL.
3. `src/mvpbi_remap/parity.py` builds, for each visual, the DAX query it effectively runs (group-by columns,
   measures, visual and page filters) against both models and compares the rows.
4. `src/mvpbi_remap/suggest.py` proposes the mapping: columns by lineage (source table and column, through the
   metric view's joins), measures by normalized name. Review it; `mapping/mapping.json` is the reviewed version
   for TPC-H, with one manual rule (the implicit customer count → the governed Customer Count measure).

## Using it on your own report

The remap and parity code is generic. Point `04_remap_report.py` at your report (edit the names in
`config.yaml` or the script), generate a mapping with `03_suggest_mapping.py`, review it, then run with
`--dry-run` first. The report must use the **PBIR** format (one `visual.json` per visual, as returned by the
Fabric `getDefinition` API); reports still in the older single-file `report.json` layout need to be converted
to PBIR first. Bookmarks, report-level measures, field parameters and calculation groups are not remapped.

## Clean up

```bash
python3 scripts/99_cleanup.py           # deletes the kit's Power BI items and drops the two metric views
```

## Layout

```
config.example.yaml    copy to config.yaml (gitignored)
scripts/               00_preflight … 05_parity_check, 99_cleanup
src/mvpbi_remap/       remap (PBIR rewriter) · parity · suggest · fabric (REST client) · config
templates/             model_a (TMDL) · report_a (PBIR) · metric_views (SQL) — rendered from config.yaml
mapping/               mapping.json (reviewed, TPC-H) · mapping.suggested.json (generated)
docs/publish.md        the manual Power BI steps
tests/                 unit tests for the rewriter, parity query builder and mapping suggester
video/                 narrated walkthrough + subtitles
```

## Third-party libraries

| Library | Purpose | License |
|---|---|---|
| [requests](https://github.com/psf/requests) | Fabric and Power BI REST calls | Apache-2.0 |
| [PyYAML](https://github.com/yaml/pyyaml) | `config.yaml` and metric view YAML parsing | MIT |
| [pytest](https://github.com/pytest-dev/pytest) | unit tests (development only) | MIT |

## License

© Databricks, Inc. Released under the [DB License](LICENSE.md). See [NOTICE.md](NOTICE.md) and [SECURITY.md](SECURITY.md).
