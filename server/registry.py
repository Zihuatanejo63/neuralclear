from __future__ import annotations

from neuralclear import AgentInfo, AgentRegistry, Capability, ResourceUnit, SettlementCredit


def build_default_registry() -> AgentRegistry:
    registry = AgentRegistry()
    registry.register(
        AgentInfo(
            agent_id="agent.pdf_summarizer",
            name="PDF Summarizer Agent",
            endpoint="http://127.0.0.1:8000",
            public_key="did:key:zExamplePdfSummarizerPublicKey",
            capabilities=[
                Capability(
                    name="summarize.pdf",
                    description="Summarize PDF text supplied by a buyer agent",
                    resource_price=ResourceUnit(1, "request"),
                    settlement_price=SettlementCredit(50, "CC"),
                )
            ],
            reputation_score=0.9,
        )
    )
    return registry


def manifest_for(agent: AgentInfo) -> dict[str, object]:
    return {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "endpoint": agent.endpoint,
        "public_key": agent.public_key,
        "capabilities": [capability.name for capability in agent.capabilities],
        "pricing": [
            {
                "capability": capability.name,
                "resource_unit": capability.resource_price.to_json(),
                "settlement_credit": capability.settlement_price.to_json(),
            }
            for capability in agent.capabilities
        ],
        "reputation": {
            "score": agent.reputation_score,
            "completed_tasks": 0,
            "dispute_rate": 0,
        },
    }
