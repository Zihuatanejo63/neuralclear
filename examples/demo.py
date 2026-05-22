from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from neuralclear import (
    AgentInfo,
    AgentRegistry,
    Capability,
    Ledger,
    NeuralClearSDK,
    ResourceUnit,
    SettlementCredit,
    SpendingMandate,
)


registry = AgentRegistry()
registry.register(
    AgentInfo(
        agent_id="agent.researcher",
        name="Research Agent",
        endpoint="https://research.example.com/a2a",
        public_key="did:key:zExamplePublicKey",
        capabilities=[
            Capability(
                name="summarize.paper",
                description="Summarize a paper from a URL",
                resource_price=ResourceUnit(8_000, "tokens"),
                settlement_price=SettlementCredit(25),
            )
        ],
        reputation_score=0.92,
    )
)

ledger = Ledger()
ledger.open_account("user.alice", SettlementCredit(100))
ledger.open_account("agent.researcher", SettlementCredit(0))

mandate = SpendingMandate(
    owner="user.alice",
    agent="agent.alice.delegate",
    allowed_capabilities=["summarize.paper"],
    max_per_task=SettlementCredit(30),
    max_daily=SettlementCredit(100),
    valid_until=(datetime.now(timezone.utc) + timedelta(days=1)).timestamp(),
    requires_human_approval_above=SettlementCredit(50),
    signature="ed25519:demo-signature",
)

sdk = NeuralClearSDK(registry, ledger)
quote = sdk.request_quote("agent.researcher", "summarize.paper")
result = sdk.call("user.alice", "agent.researcher", quote, {"url": "https://example.com/paper.pdf"}, mandate)

print(result.to_json())
print(ledger.snapshot())
