from __future__ import annotations

from copy import deepcopy

from neuralclear.core import ProtocolError


class AgentRegistryStore:
    def __init__(self) -> None:
        self._agents: dict[str, dict[str, object]] = {}

    def register(self, manifest: dict[str, object]) -> dict[str, object]:
        agent_id = str(manifest.get("agent_id", ""))
        if not agent_id:
            raise ProtocolError("agent_manifest must include agent_id")
        required = ["name", "endpoint", "public_key", "capabilities", "pricing", "reputation"]
        missing = [field for field in required if field not in manifest]
        if missing:
            raise ProtocolError(f"agent_manifest missing fields: {', '.join(missing)}")
        self._agents[agent_id] = deepcopy(manifest)
        return self.get(agent_id)

    def list_agents(self) -> list[dict[str, object]]:
        return [deepcopy(agent) for agent in self._agents.values()]

    def get(self, agent_id: str) -> dict[str, object]:
        try:
            return deepcopy(self._agents[agent_id])
        except KeyError as exc:
            raise ProtocolError(f"unknown registry agent: {agent_id}") from exc

    def search(self, capability: str) -> list[dict[str, object]]:
        return [
            deepcopy(agent)
            for agent in self._agents.values()
            if capability in list(agent.get("capabilities", []))
        ]


def build_default_registry_store() -> AgentRegistryStore:
    store = AgentRegistryStore()
    store.register(
        {
            "agent_id": "agent.pdf_summarizer",
            "name": "PDF Summarizer Agent",
            "endpoint": "http://127.0.0.1:8000",
            "public_key": "did:key:zExamplePdfSummarizerPublicKey",
            "capabilities": ["summarize.pdf"],
            "pricing": [
                {
                    "capability": "summarize.pdf",
                    "resource_unit": {"amount": 1, "unit": "request"},
                    "settlement_credit": {"amount": 50, "currency": "CC"},
                }
            ],
            "reputation": {"score": 0.9, "completed_tasks": 0, "dispute_rate": 0},
        }
    )
    return store
