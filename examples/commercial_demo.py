"""Commercial clearing demo: the revenue model, running.

Demonstrates the "marketplace transaction fee" business from
COMMERCIALIZATION.md as executable code:

  1. Marketplace operator sets a 2.5% protocol fee.
  2. Two providers compete; reputation ranks discovery.
  3. Buyer purchases through escrow clearing -> provider paid, fee collected.
  4. A bad delivery is disputed -> escrow refunds the buyer (money moves back).
  5. Operator's revenue (fee_pool) and reputation effects are printed.

Run:
    python3 examples/commercial_demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from neuralclear.clearing import (
    ClearingService,
    EscrowLedger,
    FeePolicy,
    FeeSchedule,
)
from neuralclear.core import (
    AgentRegistry,
    MockProof,
    ResourceUnit,
    SettlementCredit,
    SpendingMandate,
    TaskResult,
    Transaction,
    TransactionState,
)
from neuralclear.provider import ProviderAgent
from neuralclear.reputation import ReputationEngine


def main() -> None:
    # 1. Marketplace operator configuration: the revenue switch.
    ledger = EscrowLedger()
    ledger.open_account("owner.acme", SettlementCredit(500))
    ledger.open_account("agent.fast_summarizer", SettlementCredit(0))
    ledger.open_account("agent.cheap_summarizer", SettlementCredit(0))

    fees = FeeSchedule(FeePolicy(bps=250, minimum=1))  # 2.5%, floor 1 CC per task
    clearing = ClearingService(ledger=ledger, fees=fees)

    reputation = ReputationEngine()
    reputation.attach(clearing)  # receipts/disputes update scores automatically

    # 2. Two competing providers register.
    registry = AgentRegistry()
    providers: dict[str, ProviderAgent] = {}
    for agent_id, price in [("agent.fast_summarizer", 30), ("agent.cheap_summarizer", 20)]:
        provider = ProviderAgent(agent_id)

        @provider.capability("summarize.pdf", price=price, resource_estimate=8000)
        def summarize(payload: object, _name: str = agent_id) -> object:
            return {"summary": f"summary by {_name}", "chars": 100}

        registry.register(provider.agent_info())
        providers[agent_id] = provider

    # Seed history: fast_summarizer has a good track record.
    for _ in range(5):
        reputation.on_settled("agent.fast_summarizer", amount=30)

    ranked = reputation.rank_providers(registry, "summarize.pdf")
    print("=== Discovery, ranked by reputation ===")
    for agent in ranked:
        print(f"  {agent.agent_id:28s} score={reputation.score_of(agent.agent_id)}")

    # 3. Buyer purchases from the top-ranked provider through escrow clearing.
    mandate = SpendingMandate(
        owner="owner.acme",
        agent="buyer.assistant",
        allowed_capabilities=["summarize.pdf"],
        max_per_task=SettlementCredit(50),
        max_daily=SettlementCredit(200),
        valid_until=float("inf"),
        requires_human_approval_above=SettlementCredit(40),
        signature="ed25519:demo",
    )
    top = ranked[0]
    quote = providers[top.agent_id].handle_quote("summarize.pdf")

    def run() -> TaskResult:
        inner = providers[top.agent_id].handle_task(quote, {"text": "annual report ..."})
        return inner

    receipt = clearing.clear("owner.acme", "buyer.assistant", quote, run, mandate=mandate)
    print("\n=== Signed receipt (operator fee collected) ===")
    print(json.dumps(receipt, indent=2, default=str))

    # 4. A second task goes wrong -> dispute -> real refund.
    bad_tx = Transaction(
        sender="owner.acme",
        receiver="agent.cheap_summarizer",
        amount=SettlementCredit(20),
        fee=SettlementCredit(0),
        capability="summarize.pdf",
        state=TransactionState.QUOTE_ACCEPTED,
    )
    clearing._transactions[bad_tx.transaction_id] = bad_tx
    bad_tx.transition(TransactionState.TASK_SUBMITTED)
    ledger.hold(bad_tx)

    dispute = clearing.open_dispute(
        bad_tx.transaction_id,
        raised_by="owner.acme",
        reason="empty summary delivered",
        evidence={"result_hash": "sha256:deadbeef", "expected_min_chars": 50},
    )
    clearing.resolve_dispute(dispute.dispute_id, "refund", resolved_by="arbiter.marketplace")

    print("\n=== Dispute resolved: refund (money actually moved back) ===")
    print(json.dumps(clearing.disputes[dispute.dispute_id].to_json(), indent=2))

    # 5. Operator P&L and final state.
    print("\n=== Marketplace operator view ===")
    snap = ledger.snapshot()
    print(json.dumps(snap, indent=2))
    print(f"\nOperator revenue this session (fee_pool): {ledger.fee_pool} CC")
    print(f"Zero-sum invariant holds: {ledger.verify_zero_sum()}")
    print("\nReputation after session:")
    for agent_id in ["agent.fast_summarizer", "agent.cheap_summarizer"]:
        print(f"  {json.dumps(reputation.record(agent_id).to_json())}")


if __name__ == "__main__":
    main()
