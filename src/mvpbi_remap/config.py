"""Load config.yaml and render the templates in templates/."""
from __future__ import annotations

import pathlib
from dataclasses import dataclass

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]


@dataclass
class Config:
    profile: str
    host: str
    http_path: str
    source_catalog: str
    source_schema: str
    target_catalog: str
    target_schema: str
    workspace_id: str
    prefix: str
    model_b: str

    @property
    def source(self) -> str:
        return f"{self.source_catalog}.{self.source_schema}"

    @property
    def target(self) -> str:
        return f"{self.target_catalog}.{self.target_schema}"

    @property
    def warehouse_id(self) -> str:
        return self.http_path.rstrip("/").rsplit("/", 1)[1]

    @property
    def model_a(self) -> str:
        return self.prefix + "model_a"

    @property
    def report_a(self) -> str:
        return self.prefix + "report_a"

    def render(self, text: str) -> str:
        values = {"databricks_host": self.host, "databricks_http_path": self.http_path,
                  "source_catalog": self.source_catalog, "source_schema": self.source_schema,
                  "source": self.source, "target": self.target}
        for k, v in values.items():
            text = text.replace("{{" + k + "}}", v)
        if "{{" in text:
            raise ValueError("unrendered placeholder: " + text[text.index("{{"):][:40])
        return text


def load(path: str | pathlib.Path | None = None) -> Config:
    p = pathlib.Path(path) if path else ROOT / "config.yaml"
    if not p.exists():
        raise SystemExit(f"{p} not found: copy config.example.yaml to config.yaml and fill it in.")
    d = yaml.safe_load(p.read_text())
    host = d["databricks"]["host"].removeprefix("https://").rstrip("/")
    if "0000000000000000" in host or "0000000000000000" in d["databricks"]["http_path"] \
            or d["powerbi"]["workspace_id"].startswith("00000000-"):
        raise SystemExit("config.yaml still has placeholder values (host, http_path or workspace_id).")
    return Config(d["databricks"].get("profile", "DEFAULT"), host, d["databricks"]["http_path"],
                  d["source"]["catalog"], d["source"]["schema"], d["target"]["catalog"], d["target"]["schema"],
                  d["powerbi"]["workspace_id"], d["powerbi"].get("prefix", "tpch_demo_"),
                  d["powerbi"].get("model_b", "mv_lineitem"))


def template_parts(name: str, cfg: Config) -> dict[str, bytes]:
    """Rendered files of templates/<name>/ keyed by their item-definition path."""
    base = ROOT / "templates" / name
    out = {}
    for f in sorted(base.rglob("*")):
        if f.is_file():
            data = f.read_bytes()
            if f.suffix in (".tmdl", ".json", ".pbism"):
                data = cfg.render(data.decode()).encode()
            out[str(f.relative_to(base))] = data
    return out
