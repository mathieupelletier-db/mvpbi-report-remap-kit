# Repoint a Power BI report to Unity Catalog metric views

You can move the business logic of a Power BI semantic model to Unity Catalog metric views. Genie Code
`/importBI` makes the metric views. Publish to Power BI makes a new semantic model from the metric views.
But the old report still points at the old semantic model.

A rebind of the old report to the new model does not work. A published metric view is one table, with the
name of the metric view and its field names. The old report uses the old tables and field names, for example
`nation[n_name]` and `lineitem[Total Revenue]`. Thus, each visual shows an error after a rebind.

This kit changes the field references in the report definition. It changes the visuals, filters, sorts,
slicers and implicit measures. Then it uploads the report with a link to the published metric views. The
report keeps its ID and its URL. Then the kit compares the data of each visual through the two models.

The kit uses the TPC-H sample tables that are in all Unity Catalog workspaces (`samples.tpch`). Thus, you can
try the full procedure before you change a real report.

> This kit is a sample under the [DB License](LICENSE.md). Databricks does not support it
> (refer to [NOTICE.md](NOTICE.md)). At this time, Publish to Power BI for metric views is in **Private
> Preview**. Your Databricks account team must enroll your workspace. Then a workspace admin must turn on
> the preview.

https://github.com/user-attachments/assets/49f631f9-ece3-4c89-9ed3-75aca71b0b02

*The video uses a copy of TPC-H at scale factor 10. The kit uses `samples.tpch` by default. Thus, your
numbers are different. Subtitles: [video/…narrated.srt](video/mvpbi-report-remap-walkthrough-narrated.srt).*

## Contents of the kit

| | |
|---|---|
| Model A + Report A | A Power BI semantic model on TPC-H with a star schema: 8 tables, 7 relationships and 4 DAX measures, in DirectQuery mode on Databricks SQL. A report with 5 pages and 17 visuals, with visual filters, page filters, sorts and slicers. |
| Metric views | `mv_lineitem` (line-item grain, with the 4 measures) and `mv_customer` (customer grain). Both are ready to publish. |
| Remap | A script that changes Report A to use the published semantic model (Model B). It can change Report A or make a new report. |
| Parity check | A DAX comparison of each visual between Model A and Model B, and a report of all the parts that the script did not change. |

## Prerequisites

- **Databricks:**
  - A Unity Catalog workspace with the *Publish Metric View To Powerbi* preview (Settings > Previews).
  - A SQL warehouse.
  - The `CREATE SCHEMA` privilege on a catalog.
  - The [Databricks CLI](https://docs.databricks.com/dev-tools/cli/), with a login (`databricks auth login --profile <name>`).
- **Power BI:**
  - A workspace on Premium, Premium Per User or Fabric capacity, with the XMLA endpoint set to *Read Write*.
  - The Contributor role or a higher role in this workspace.
  - The [Azure CLI](https://learn.microsoft.com/cli/azure/), with a login to the same Microsoft Entra tenant (`az login`).
- **Local computer:** Python 3.10 or later. Run `pip install -r requirements.txt`.

The kit does not keep secrets. The SQL statements use your Databricks CLI profile. The Power BI calls use
your `az login` session.

## Procedure

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

`02_deploy_powerbi.py` can show that Model A cannot query Databricks. In this case, set the data source
credentials of Model A one time (docs/publish.md, step 0). Then run the script again.

## Expected result

With TPC-H, the script changes **17 of the 18 report parts**. **All 16 changed visuals return the same rows**
through Model B. The script does not change one visual and three slicer connections. It shows them in a
report:

- **Visuals with two facts.** Each published metric view is a separate Power BI table, without relationships
  between the tables. Thus, a visual can use only one of these tables. `trend / table_top_nations` uses
  Avg Order Value (`mv_lineitem`) and a customer count (`mv_customer`). The script does not change this visual,
  and it shows the visual in the report.
- **Slicers and page filters** filter only the visuals that use the same table. `out/remap.md` shows each case.
- **Grain changes in implicit measures.** Report A counts `customer[c_custkey]`. This count includes the customers
  that have no orders. At line-item grain, this count changes. Thus, the kit has a separate metric view at
  customer grain. Also, the script maps the columns on lineage, not on their names.
- **The (Blank) member.** The slicers of Model A show a virtual "(Blank)" member. Power BI adds this member for
  DirectQuery relationships. Model B does not have this member. The parity check shows this difference as a
  match, and it adds a note.

## How the kit works

1. `src/mvpbi_remap/remap.py` reads the report definition (PBIR). It changes each field reference with the
   rules in a mapping file (`mapping/mapping.json`). It changes the visual fields, the filters with aliases,
   the sort definitions, the selector text and the implicit aggregations. For each visual, it selects the one
   published table that contains all the fields of the visual. It keeps the labels, and also the default
   Power BI label of implicit measures ("Count of c_custkey").
2. `04_remap_report.py` uploads the changed definition with the Fabric REST API (`updateDefinition`). The upload
   includes a new dataset reference. Power BI keeps the ID and the URL of the report.
3. `src/mvpbi_remap/parity.py` makes the DAX query of each visual. The query contains the columns that group the
   data, the measures, the visual filters and the page filters. The script runs the query on the two models and compares
   the rows.
4. `src/mvpbi_remap/suggest.py` makes a proposal for the mapping file. It maps the columns on lineage: the source table
   and the source column, through the joins of the metric view. It maps the measures on their names. Examine the
   proposal before you use it. `mapping/mapping.json` is the examined version for TPC-H. It has one manual rule:
   the implicit customer count becomes the governed Customer Count measure.

## Use the kit on your own report

The remap code and the parity code are not specific to TPC-H. To use them on your own report, do these steps:

1. Write the names of your report and models in `config.yaml`, or in the script.
2. Make the mapping file with `03_suggest_mapping.py`.
3. Examine the mapping file.
4. Run `04_remap_report.py --dry-run` first.

The report must use the **PBIR** format, with one `visual.json` file for each visual. The Fabric `getDefinition`
API returns this format. Convert reports in the older single-file format (`report.json`) to PBIR first. The
script does not change bookmarks, report-level measures, field parameters or calculation groups.

## Clean up

```bash
python3 scripts/99_cleanup.py           # deletes the kit's Power BI items and drops the two metric views
```

## Structure of the repository

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
| [requests](https://github.com/psf/requests) | Calls to the Fabric and Power BI REST APIs | Apache-2.0 |
| [PyYAML](https://github.com/yaml/pyyaml) | Read `config.yaml` and the metric view YAML | MIT |
| [pytest](https://github.com/pytest-dev/pytest) | Unit tests (for development only) | MIT |

## License

© Databricks, Inc. This kit is under the [DB License](LICENSE.md). Refer to [NOTICE.md](NOTICE.md) and [SECURITY.md](SECURITY.md).
