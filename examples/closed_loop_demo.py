"""THE REAL CLOSED LOOP — one command, the whole clearing economy.

What actually runs (no mocks at the transport layer):

  [1] Two provider agents start as real HTTP servers (threads, real sockets)
  [2] Buyer discovers them by fetching /.well-known manifests over HTTP
  [3] Single task: quote -> mandate -> escrow hold -> HTTP execution
      -> proof -> release -> signed receipt          (the retail flow)
  [4] Netting channel: 1 deposit -> 100 hash-chained micro-tasks over HTTP
      -> 1 net settlement                            (the x402-wedge flow)
  [5] Dispute: a held transaction resolves to refund — money moves back
  [6] SQLite persistence: state saved, process-equivalent reload verified

Run:
    python3 examples/closed_loop_demo.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from neuralclear.buyer import BuyerAgent
from neuralclear.clearing import ClearingService, EscrowLedger, FeePolicy, FeeSchedule
from neuralclear.core import (
    AgentRegistry,
    SettlementCredit,
    SpendingMandate,
    Transaction,
    TransactionState,
)
from neuralclear.httpwire import ProviderHTTPServer, RemoteProvider
from neuralclear.netting import NettingService
from neuralclear.provider import ProviderAgent
from neuralclear.reputation import ReputationEngine
from neuralclear.store import ClearingStore


def hr(title: str) -> None:
    print(f"\n{'=' * 64}\n{title}\n{'=' * 64}")


def main() -> None:
    # ----------------------------------------------------------------- [1]
    hr("[1] Providers go live as real HTTP services")
    research = ProviderAgent("agent.research_pro", name="Research Pro")

    @research.capability("market.research", price=40, resource_estimate=12000, resource_unit="tokens")
    def do_research(payload: object) -> object:
        topic = payload.get("topic", "?") if isinstance(payload, dict) else "?"
        return {"report": f"Market analysis of {topic}: demand is accelerating.", "pages": 6}

    micro = ProviderAgent("agent.embedder", name="Embedding Service")

    @micro.capability("embed.text", price=1, resource_estimate=1, resource_unit="calls")
    def do_embed(payload: object) -> object:
        text = payload.get("text", "") if isinstance(payload, dict) else str(payload)
        return {"dim": 768, "norm": round(sum(map(ord, text)) % 100 / 100, 2)}

    server_a = ProviderHTTPServer(research).start()
    server_b = ProviderHTTPServer(micro).start()
    print(f"  research provider  -> {server_a.url}")
    print(f"  embedding provider -> {server_b.url}")

    # ----------------------------------------------------------------- [2]
    hr("[2] Buyer discovers providers over HTTP (.well-known)")
    ledger = EscrowLedger()
    ledger.open_account("owner.acme", SettlementCredit(500))
    ledger.open_account("agent.research_pro", SettlementCredit(0))
    ledger.open_account("agent.embedder", SettlementCredit(0))

    fees = FeeSchedule(FeePolicy(bps=250, minimum=1))  # 2.5%, floor 1 CC
    clearing = ClearingService(ledger=ledger, fees=fees)
    reputation = ReputationEngine()
    reputation.attach(clearing)

    registry = AgentRegistry()
    buyer = BuyerAgent("buyer.assistant", registry=registry, ledger=ledger, owner="owner.acme")
    for url in (server_a.url, server_b.url):
        agent_id = buyer.connect_remote(url)
        print(f"  discovered {agent_id} (manifest fetched over HTTP)")

    # ----------------------------------------------------------------- [3]
    hr("[3] Retail flow: one task through full escrow clearing")
    mandate = SpendingMandate(
        owner="owner.acme",
        agent="buyer.assistant",
        allowed_capabilities=["market.research", "embed.text"],
        max_per_task=SettlementCredit(50),
        max_daily=SettlementCredit(300),
        valid_until=float("inf"),
        requires_human_approval_above=SettlementCredit(45),
        signature="ed25519:demo",
    )
    remote_research = RemoteProvider(server_a.url)
    quote = remote_research.handle_quote("market.research")
    print(f"  quote over HTTP: {quote.settlement_price.amount} CC for {quote.capability}")

    receipt = clearing.clear(
        "owner.acme",
        "buyer.assistant",
        quote,
        run=lambda: remote_research.handle_task(quote, {"topic": "agent clearing"}),
        mandate=mandate,
    )
    print(f"  escrow held -> task executed over HTTP -> released")
    print(f"  signed receipt {receipt['receipt_id']}: amount={receipt['amount']} fee={receipt['fee']}")
    print(f"  signature valid: {clearing.signer.verify(receipt)}")

    # ----------------------------------------------------------------- [4]
    hr("[4] Netting flow: 100 micro-tasks, ONE settlement")
    netting = NettingService(clearing)
    channel = netting.open_channel("owner.acme", "agent.embedder", deposit=120)
    print(f"  channel {channel.channel_id[:18]}… opened, deposit=120 CC held in escrow")

    remote_micro = RemoteProvider(server_b.url)
    micro_quote = remote_micro.handle_quote("embed.text")
    for index in range(100):
        payload = {"text": f"document chunk {index}"}
        result = remote_micro.handle_task(micro_quote, payload)  # real HTTP each call
        payload_hash = hashlib.sha256(
            json.dumps({"in": payload, "out": result.output}, sort_keys=True).encode()
        ).hexdigest()
        channel.meter("embed.text", amount=1, payload_hash=f"sha256:{payload_hash[:16]}")

    print(f"  100 tasks metered over HTTP, chain verified: {channel.verify_chain()}")
    net_receipt = netting.settle(channel.channel_id)
    print(f"  ONE net settlement: provider +{net_receipt['net_to_provider']}, "
          f"buyer refunded {net_receipt['refunded_to_buyer']}, fee {net_receipt['protocol_fee']}")
    stats = netting.settlement_savings(channel.channel_id, per_settlement_cost=0.001)
    print(f"  settlements avoided: {stats['settlements_avoided']} "
          f"(cost reduction {stats['cost_reduction_factor']}x)")

    # ----------------------------------------------------------------- [5]
    hr("[5] Dispute: held funds actually move back")
    bad_tx = Transaction(
        sender="owner.acme",
        receiver="agent.research_pro",
        amount=SettlementCredit(30),
        fee=SettlementCredit(1),
        capability="market.research",
        state=TransactionState.QUOTE_ACCEPTED,
    )
    clearing._transactions[bad_tx.transaction_id] = bad_tx
    bad_tx.transition(TransactionState.TASK_SUBMITTED)
    ledger.hold(bad_tx)
    before = ledger.balance_of("owner.acme")
    dispute = clearing.open_dispute(bad_tx.transaction_id, "owner.acme", "report never delivered")
    clearing.resolve_dispute(dispute.dispute_id, "refund", "arbiter.alpha")
    print(f"  buyer balance {before} -> {ledger.balance_of('owner.acme')} (escrow refunded)")

    # ----------------------------------------------------------------- [6]
    hr("[6] Persistence: clearing state survives a restart")
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "clearing.db"
        ClearingStore(db).save(clearing)
        restored = ClearingStore(db).load()
        match = (
            restored.ledger.balances == ledger.balances
            and restored.ledger.fee_pool == ledger.fee_pool
            and restored.ledger.verify_zero_sum()
        )
        print(f"  saved to SQLite, reloaded fresh service: state identical = {match}")
        any_receipt = next(iter(restored.receipts.values()))
        print(f"  reloaded receipt signature still valid: {clearing.signer.verify(any_receipt)}")

    # ----------------------------------------------------------------- end
    hr("FINAL STATE")
    print(json.dumps(ledger.snapshot(), indent=2))
    print(f"\nProtocol revenue (fee_pool): {ledger.fee_pool} CC")
    print(f"Zero-sum invariant: {ledger.verify_zero_sum()}")
    print(f"Events emitted: {len(clearing.events.history)}")
    print("Reputation:")
    for agent_id in ("agent.research_pro", "agent.embedder"):
        print(f"  {json.dumps(reputation.record(agent_id).to_json())}")

    server_a.stop()
    server_b.stop()


if __name__ == "__main__":
    main()
