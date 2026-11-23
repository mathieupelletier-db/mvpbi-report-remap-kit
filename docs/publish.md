# Manual steps in Power BI and Databricks

## Step 0 (only if necessary): Set the data source credentials of Model A

`02_deploy_powerbi.py` makes Model A with the Fabric REST API. Power BI needs credentials for the DirectQuery
source of Model A one time. Do this step only if the script shows that Model A cannot query Databricks.

1. In Power BI, open your workspace.
2. Find **`<prefix>model_a`**.
3. Select **⋯** > **Settings**.
4. Select **Data source credentials** > **Edit credentials**.
5. Set the authentication method to **OAuth2**.
6. Select **Sign in**.
7. Run `python3 02_deploy_powerbi.py` again. The last line shows the orders and the revenue from Model A.

## Step 3½: Publish the metric views to Power BI

Do this step after `01_create_metric_views.py` and `02_deploy_powerbi.py`, and before `04_remap_report.py`.
The *Publish Metric View To Powerbi* preview must be on in your Databricks workspace.

**Publish `mv_lineitem` as a new semantic model:**

1. In Databricks, open **Catalog**.
2. Open your target catalog and schema, then open **`mv_lineitem`**.
3. If the catalog pane asks for a SQL warehouse, select your SQL warehouse.
4. Select **Publish to Power BI** (at the top right).
5. If the dialog shows **Connect to Microsoft Entra ID**, select it and give consent.
6. In **Power BI workspace**, select the workspace from `config.yaml`.
7. In **Power BI semantic model**, select *Publish new semantic model*.
8. In **Storage mode**, select *DirectQuery*.
9. In **Authentication method**, select *OAuth*.
10. Select **Publish to Power BI**.
11. Wait for the message *Successfully published semantic model*.

A new workspace can take some minutes to show in the list. If your workspace is not in the list, close the
dialog and open it again.

The dialog does not show the warning "measures need dimensions" for `mv_lineitem` of this kit. The metric
view already shows all the columns that its measures read. You can see this warning when you publish a metric
view that `/importBI` made. In this case, select **Fix and publish**. This button adds the necessary dimensions.
Then examine the measure formats, and add the formats that the button removed.

**Publish `mv_customer` to the same semantic model:**

1. Open **`mv_customer`** in the same schema.
2. Select **Publish to Power BI**.
3. Select the same workspace.
4. Select **Update an existing semantic model**.
5. Select **`mv_lineitem`**.
6. Select **Publish to Power BI**.

The name of the semantic model is `mv_lineitem`. It has two tables, `mv_lineitem` and `mv_customer`. There are
no relationships between these tables. If you use a different name, set `powerbi.model_b` in `config.yaml`.
