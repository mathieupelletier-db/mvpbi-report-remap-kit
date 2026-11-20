"""Minimal Fabric + Power BI REST client using the az CLI login (no secrets stored)."""
import base64
import json
import subprocess
import time

import requests

FABRIC = "https://api.fabric.microsoft.com/v1"
PBI = "https://api.powerbi.com/v1.0/myorg"
FABRIC_RES = "https://api.fabric.microsoft.com"
PBI_RES = "https://analysis.windows.net/powerbi/api"


class Client:
    def __init__(self, workspace_id: str) -> None:
        self.ws = workspace_id
        self._tok: dict[str, str] = {}

    def _token(self, res: str) -> str:
        if res not in self._tok:
            out = subprocess.run(
                ["az", "account", "get-access-token", "--resource", res,
                 "--query", "accessToken", "-o", "tsv"],
                capture_output=True, text=True, check=True)
            self._tok[res] = out.stdout.strip()
        return self._tok[res]

    def req(self, method: str, url: str, body=None, res: str = FABRIC_RES) -> requests.Response:
        h = {"Authorization": f"Bearer {self._token(res)}", "Content-Type": "application/json"}
        data = json.dumps(body) if body is not None else None
        if data is None:
            h["Content-Length"] = "0"
        return requests.request(method, url, headers=h, data=data, timeout=120)

    def lro(self, r: requests.Response, timeout: float = 600) -> dict:
        if r.status_code != 202:
            if not r.ok:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:800]}")
            return r.json() if r.text else {}
        loc, wait = r.headers["Location"], int(r.headers.get("Retry-After", "3"))
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            time.sleep(wait)
            st = self.req("GET", loc).json()
            if st.get("status") == "Succeeded":
                res = self.req("GET", loc.rstrip("/") + "/result")
                return res.json() if res.text else {}
            if st.get("status") in ("Failed", "Undetermined"):
                raise RuntimeError(f"LRO failed: {json.dumps(st)[:800]}")
        raise TimeoutError(loc)

    # ---- items -------------------------------------------------------------
    def items(self, item_type: str | None = None) -> list[dict]:
        url = f"{FABRIC}/workspaces/{self.ws}/items" + (f"?type={item_type}" if item_type else "")
        out, cont = [], None
        while True:
            r = self.req("GET", url + (("&" if "?" in url else "?") + f"continuationToken={cont}" if cont else ""))
            r.raise_for_status()
            d = r.json()
            out += d.get("value", [])
            cont = d.get("continuationToken")
            if not cont:
                return out

    def find(self, name: str, item_type: str) -> dict | None:
        return next((i for i in self.items(item_type) if i["displayName"] == name), None)

    def get_definition(self, item_id: str, fmt: str | None = None) -> dict[str, bytes]:
        url = f"{FABRIC}/workspaces/{self.ws}/items/{item_id}/getDefinition" + (f"?format={fmt}" if fmt else "")
        d = self.lro(self.req("POST", url))
        return {p["path"]: base64.b64decode(p["payload"]) for p in d["definition"]["parts"]}

    @staticmethod
    def _parts(parts: dict[str, bytes]) -> list[dict]:
        return [{"path": k, "payload": base64.b64encode(v).decode(), "payloadType": "InlineBase64"}
                for k, v in parts.items()]

    def create(self, name: str, item_type: str, parts: dict[str, bytes]) -> dict:
        body = {"displayName": name, "type": item_type, "definition": {"parts": self._parts(parts)}}
        return self.lro(self.req("POST", f"{FABRIC}/workspaces/{self.ws}/items", body))

    def update_definition(self, item_id: str, parts: dict[str, bytes]) -> dict:
        url = f"{FABRIC}/workspaces/{self.ws}/items/{item_id}/updateDefinition"
        return self.lro(self.req("POST", url, {"definition": {"parts": self._parts(parts)}}))

    # ---- power bi ----------------------------------------------------------
    def dax(self, dataset_id: str, query: str) -> list[dict]:
        url = f"{PBI}/groups/{self.ws}/datasets/{dataset_id}/executeQueries"
        r = self.req("POST", url, {"queries": [{"query": query}],
                                   "serializerSettings": {"includeNulls": True}}, res=PBI_RES)
        d = r.json()
        if "results" not in d:
            raise RuntimeError(json.dumps(d.get("error", d))[:1200])
        t = d["results"][0]["tables"][0]
        if "error" in t:
            raise RuntimeError(json.dumps(t["error"])[:1200])
        return t.get("rows", [])

    def report(self, report_id: str) -> dict:
        return self.req("GET", f"{PBI}/groups/{self.ws}/reports/{report_id}", res=PBI_RES).json()

    def rebind(self, report_id: str, dataset_id: str) -> requests.Response:
        return self.req("POST", f"{PBI}/groups/{self.ws}/reports/{report_id}/Rebind",
                        {"datasetId": dataset_id}, res=PBI_RES)
