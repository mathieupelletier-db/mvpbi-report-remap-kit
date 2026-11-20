"""Create (or update) Model A and Report A in the Power BI workspace, then smoke-test Model A."""
import json

from _common import Client, load, template_parts

cfg = load()
c = Client(cfg.workspace_id)

model_parts = template_parts("model_a", cfg)
model = c.find(cfg.model_a, "SemanticModel")
if model:
    c.update_definition(model["id"], model_parts)
else:
    c.create(cfg.model_a, "SemanticModel", model_parts)
    model = c.find(cfg.model_a, "SemanticModel")
print("Model A:", cfg.model_a, model["id"])

report_parts = template_parts("report_a", cfg)
report_parts["definition.pbir"] = json.dumps({
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
    "version": "4.0", "datasetReference": {"byConnection": {"connectionString": f"semanticmodelid={model['id']}"}}},
    indent=2).encode()
report = c.find(cfg.report_a, "Report")
if report:
    c.update_definition(report["id"], report_parts)
else:
    c.create(cfg.report_a, "Report", report_parts)
    report = c.find(cfg.report_a, "Report")
print("Report A:", cfg.report_a, report["id"])

try:
    row = c.dax(model["id"], 'EVALUATE ROW("orders", [Order Count], "revenue", [Total Revenue])')[0]
    print(f"smoke test (DirectQuery through Model A): {row}")
except RuntimeError as e:
    print("Model A could not query Databricks yet:", str(e)[:300])
    print("Set its data source credentials once: Power BI > workspace > Model A > Settings > Data source credentials\n"
          "> Edit credentials > OAuth2, sign in, then re-run this script.")
    raise SystemExit(1)
