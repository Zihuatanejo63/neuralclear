from __future__ import annotations

import json
from urllib import request


class NeuralClearHTTPClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def get_manifest(self) -> dict[str, object]:
        return self._get("/.well-known/neuralclear/agent.json")

    def request_quote(self, buyer: str, provider: str, capability: str) -> dict[str, object]:
        return self._post(
            "/neuralclear/quote",
            {"buyer": buyer, "provider": provider, "capability": capability},
        )

    def submit_task(self, body: dict[str, object]) -> dict[str, object]:
        return self._post("/neuralclear/tasks", body)

    def get_task(self, task_id: str) -> dict[str, object]:
        return self._get(f"/neuralclear/tasks/{task_id}")

    def open_dispute(self, body: dict[str, object]) -> dict[str, object]:
        return self._post("/neuralclear/disputes", body)

    def get_receipt(self, receipt_id: str) -> dict[str, object]:
        return self._get(f"/neuralclear/receipts/{receipt_id}")

    def list_receipts(self) -> list[dict[str, object]]:
        return self._get("/neuralclear/receipts")

    def balances(self) -> dict[str, object]:
        return self._get("/neuralclear/balances")

    def list_agents(self) -> list[dict[str, object]]:
        return self._get("/registry/agents")

    def search_agents(self, capability: str) -> list[dict[str, object]]:
        return self._get(f"/registry/search?capability={capability}")

    def register_agent(self, manifest: dict[str, object]) -> dict[str, object]:
        return self._post("/registry/agents", manifest)

    def _get(self, path: str):
        with request.urlopen(f"{self.base_url}{path}", timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post(self, path: str, body: dict[str, object]) -> dict[str, object]:
        data = json.dumps(body).encode("utf-8")
        req = request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
