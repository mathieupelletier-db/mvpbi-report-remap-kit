# Manual steps in Power BI and Databricks

## Step 0 (only if needed): sign in Model A's data source

`02_deploy_powerbi.py` creates Model A with the Fabric REST API. Power BI needs credentials for its
DirectQuery source once. If the script reports that Model A cannot query Databricks:

1. In Power BI, open your workspace, find **`<prefix>model_a`** → **⋯** → **Settings**.
2. **Data source credentials** → **Edit credentials** → Authentication method **OAuth2** → **Sign in**.
3. Run `python3 02_deploy_powerbi.py` again; it ends with a smoke-test row of orders and revenue.

## Step 3½: publish the metric views to Power BI

Run this after `01_create_metric_views.py` and `02_deploy_powerbi.py`, before `04_remap_report.py`.
It needs the *Publish Metric View To Powerbi* preview on in your Databricks workspace.

**First `mv_lineitem`, as a new semantic model:**

1. In Databricks, open **Catalog** → your target catalog and schema → **`mv_lineitem`**.
2. Select your SQL warehouse at the top of the catalog pane if prompted.
3. Click **Publish to Power BI** (top right). If asked, click **Connect to Microsoft Entra ID** and consent.
4. **Power BI workspace:** the workspace from `config.yaml`. A workspace created a few minutes ago can take a
   moment to appear in the list; reopen the dialog if it is missing.
5. **Power BI semantic model:** *Publish new semantic model*. **Storage mode:** *DirectQuery*.
   **Authentication method:** *OAuth*.
6. Click **Publish to Power BI** and wait for *Successfully published semantic model*.

No "measures need dimensions" warning should appear: the kit's `mv_lineitem` already exposes every column its
measures read. If you publish a view produced by `/importBI` yourself and see that warning, **Fix and publish**
adds the missing dimensions for you (check the measure formats afterwards; re-add any it dropped).

**Then `mv_customer`, into the same semantic model:**

1. Open **`mv_customer`** in the same schema → **Publish to Power BI**.
2. Same workspace, then **Update an existing semantic model** → choose **`mv_lineitem`**.
3. **Publish to Power BI**.

The semantic model is named `mv_lineitem` and holds two tables, `mv_lineitem` and `mv_customer`, with no
relationships between them. If you name it differently, set `powerbi.model_b` in `config.yaml`.
