"""Tests for the commercial clearing layer and reputation engine."""

from __future__ import annotations

import unittest

from neuralclear.clearing import (
    EVENT_DISPUTE_OPENED,
    EVENT_DISPUTE_RESOLVED,
    EVENT_RECEIPT_CREATED,
    EVENT_TRANSACTION_HELD,
    ClearingService,
    EscrowLedger,
    FeePolicy,
    FeeSchedule,
    ReceiptSigner,
)
from neuralclear.core import (
    AgentRegistry,
    MockProof,
    ProtocolError,
    Quote,
    ResourceUnit,
    SettlementCredit,
    SpendingMandate,
    TaskResult,
    Transaction,
    TransactionState,
)
from neuralclear.provider import ProviderAgent
from neuralclear.reputation import ReputationEngine


def make_quote(provider: str = "agent.worker", price: int = 100, capability: str = "summarize.pdf") -> Quote:
    return Quote(
        provider=provider,
        capability=capability,
        resource_estimate=ResourceUnit(1000, "tokens"),
        settlement_price=SettlementCredit(price),
        expires_at=float("inf"),
    )


def make_result(tx_id: str = "", amount: int = 100) -> TaskResult:
    return TaskResult(
        transaction_id=tx_id,
        output={"ok": True},
        resource_usage=[ResourceUnit(900, "tokens")],
        settlement_amount=SettlementCredit(amount),
        proof=MockProof(),
    )


def funded_ledger(buyer: str = "owner.acme", provider: str = "agent.worker", funds: int = 1000) -> EscrowLedger:
    ledger = EscrowLedger()
    ledger.open_account(buyer, SettlementCredit(funds))
    ledger.open_account(provider, SettlementCredit(0))
    return ledger


class FeePolicyTests(unittest.TestCase):
    def test_bps_plus_flat_with_minimum(self) -> None:
        policy = FeePolicy(bps=250, flat=1, minimum=2)
        self.assertEqual(policy.fee_for(SettlementCredit(100)).amount, 3)  # 2.5->2 +1
        self.assertEqual(policy.fee_for(SettlementCredit(10)).amount, 2)   # floor at minimum

    def test_fee_cannot_consume_amount(self) -> None:
        with self.assertRaises(ProtocolError):
            FeePolicy(bps=10_000).fee_for(SettlementCredit(10))

    def test_invalid_policies_rejected(self) -> None:
        with self.assertRaises(ProtocolError):
            FeePolicy(bps=-1)
        with self.assertRaises(ProtocolError):
            FeePolicy(bps=10_001)

    def test_schedule_override(self) -> None:
        schedule = FeeSchedule(FeePolicy(bps=100))
        schedule.set_capability_fee("train.model", FeePolicy(bps=500))
        self.assertEqual(schedule.policy_for("summarize.pdf").bps, 100)
        self.assertEqual(schedule.policy_for("train.model").bps, 500)


class EscrowLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = funded_ledger()
        self.tx = Transaction(
            sender="owner.acme",
            receiver="agent.worker",
            amount=SettlementCredit(100),
            fee=SettlementCredit(3),
            capability="summarize.pdf",
            state=TransactionState.QUOTE_ACCEPTED,
        )
        self.tx.transition(TransactionState.TASK_SUBMITTED)

    def test_hold_locks_funds_zero_sum(self) -> None:
        self.ledger.hold(self.tx)
        self.assertEqual(self.ledger.balance_of("owner.acme"), 897)
        self.assertEqual(self.ledger.escrow_total(), 103)
        self.assertTrue(self.ledger.verify_zero_sum())

    def test_release_pays_provider_and_fee_pool(self) -> None:
        self.ledger.hold(self.tx)
        self.tx.transition(TransactionState.TASK_RUNNING)
        self.tx.transition(TransactionState.RESULT_DELIVERED)
        self.tx.transition(TransactionState.PROOF_VERIFIED)
        self.ledger.release(self.tx)
        self.assertEqual(self.ledger.balance_of("agent.worker"), 100)
        self.assertEqual(self.ledger.fee_pool, 3)
        self.assertEqual(self.ledger.escrow_total(), 0)
        self.assertEqual(self.tx.state, TransactionState.SETTLED)
        self.assertTrue(self.ledger.verify_zero_sum())

    def test_refund_returns_money_to_buyer(self) -> None:
        """The critical fix: refund must move money, not just state."""
        self.ledger.hold(self.tx)
        self.tx.transition(TransactionState.DISPUTED)
        self.ledger.refund_escrow(self.tx)
        self.assertEqual(self.ledger.balance_of("owner.acme"), 1000)  # fully restored
        self.assertEqual(self.ledger.balance_of("agent.worker"), 0)
        self.assertEqual(self.tx.state, TransactionState.REFUNDED)
        self.assertTrue(self.ledger.verify_zero_sum())

    def test_slash_moves_escrow_to_fee_pool(self) -> None:
        self.ledger.hold(self.tx)
        self.tx.transition(TransactionState.DISPUTED)
        self.ledger.slash_escrow(self.tx)
        self.assertEqual(self.ledger.fee_pool, 103)
        self.assertEqual(self.tx.state, TransactionState.SLASHED)
        self.assertTrue(self.ledger.verify_zero_sum())

    def test_split_divides_escrow(self) -> None:
        self.ledger.hold(self.tx)
        self.tx.transition(TransactionState.DISPUTED)
        self.ledger.split_escrow(self.tx, provider_amount=40)
        self.assertEqual(self.ledger.balance_of("agent.worker"), 40)
        self.assertEqual(self.ledger.balance_of("owner.acme"), 957)  # 897 + 60 back
        self.assertEqual(self.ledger.fee_pool, 3)
        self.assertTrue(self.ledger.verify_zero_sum())

    def test_hold_insufficient_credit(self) -> None:
        poor = EscrowLedger()
        poor.open_account("owner.broke", SettlementCredit(50))
        with self.assertRaises(ProtocolError):
            poor.hold(self.tx)

    def test_double_hold_rejected(self) -> None:
        self.ledger.hold(self.tx)
        with self.assertRaises(ProtocolError):
            self.ledger.hold(self.tx)

    def test_release_without_hold_rejected(self) -> None:
        with self.assertRaises(ProtocolError):
            self.ledger.release(self.tx)


class ClearingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = funded_ledger()
        self.fees = FeeSchedule(FeePolicy(bps=250))  # 2.5% protocol fee
        self.svc = ClearingService(ledger=self.ledger, fees=self.fees)

    def test_clear_collects_protocol_fee(self) -> None:
        quote = make_quote(price=100)
        receipt = self.svc.clear("owner.acme", "buyer.bot", quote, lambda: make_result())
        self.assertEqual(self.ledger.balance_of("agent.worker"), 100)
        self.assertEqual(self.ledger.fee_pool, 2)  # 2.5% of 100 -> 2
        self.assertEqual(receipt["fee"], 2)
        self.assertTrue(self.ledger.verify_zero_sum())

    def test_receipt_is_signed_and_verifiable(self) -> None:
        quote = make_quote()
        receipt = self.svc.clear("owner.acme", "buyer.bot", quote, lambda: make_result())
        self.assertTrue(self.svc.signer.verify(receipt))
        tampered = dict(receipt)
        tampered["amount"] = 1
        self.assertFalse(self.svc.signer.verify(tampered))

    def test_events_emitted_in_order(self) -> None:
        quote = make_quote()
        self.svc.clear("owner.acme", "buyer.bot", quote, lambda: make_result())
        names = [event for event, _ in self.svc.events.history]
        self.assertEqual(names, [EVENT_TRANSACTION_HELD, EVENT_RECEIPT_CREATED])

    def test_mandate_includes_fee_in_budget_check(self) -> None:
        mandate = SpendingMandate(
            owner="owner.acme",
            agent="buyer.bot",
            allowed_capabilities=["summarize.pdf"],
            max_per_task=SettlementCredit(100),  # price 100 + fee 2 > 100 -> blocked
            max_daily=SettlementCredit(1000),
            valid_until=float("inf"),
            requires_human_approval_above=SettlementCredit(100),
            signature="ed25519:test",
        )
        with self.assertRaises(ProtocolError):
            self.svc.clear("owner.acme", "buyer.bot", make_quote(price=100), lambda: make_result(), mandate)

    def test_failed_proof_auto_refunds(self) -> None:
        class BadProof(MockProof):
            def verify(self) -> bool:
                return False

        def run() -> TaskResult:
            result = make_result()
            return TaskResult(
                transaction_id=result.transaction_id,
                output=result.output,
                resource_usage=result.resource_usage,
                settlement_amount=result.settlement_amount,
                proof=BadProof(),
            )

        with self.assertRaises(ProtocolError):
            self.svc.clear("owner.acme", "buyer.bot", make_quote(), run)
        self.assertEqual(self.ledger.balance_of("owner.acme"), 1000)  # money back
        self.assertEqual(self.ledger.escrow_total(), 0)


class DisputeFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = funded_ledger()
        self.svc = ClearingService(ledger=self.ledger, fees=FeeSchedule(FeePolicy(bps=0)))

    def _held_transaction(self) -> str:
        """Create a transaction frozen in escrow (dispute before release)."""
        quote = make_quote(price=100)

        captured: dict[str, str] = {}

        def run() -> TaskResult:
            # open the dispute mid-flight is awkward; instead clear normally then
            # use a second path: hold manually for dispute-stage tests
            return make_result()

        # Build a held transaction directly through service internals
        tx = Transaction(
            sender="owner.acme",
            receiver="agent.worker",
            amount=SettlementCredit(100),
            fee=SettlementCredit(0),
            capability="summarize.pdf",
            state=TransactionState.QUOTE_ACCEPTED,
        )
        self.svc._transactions[tx.transaction_id] = tx
        tx.transition(TransactionState.TASK_SUBMITTED)
        self.ledger.hold(tx)
        captured["id"] = tx.transaction_id
        return captured["id"]

    def test_dispute_refund_resolution(self) -> None:
        tx_id = self._held_transaction()
        dispute = self.svc.open_dispute(tx_id, "owner.acme", "result was empty")
        resolved = self.svc.resolve_dispute(dispute.dispute_id, "refund", "arbiter.alpha")
        self.assertEqual(resolved.resolution, "refund")
        self.assertEqual(self.ledger.balance_of("owner.acme"), 1000)
        names = [event for event, _ in self.svc.events.history]
        self.assertIn(EVENT_DISPUTE_OPENED, names)
        self.assertIn(EVENT_DISPUTE_RESOLVED, names)

    def test_dispute_split_resolution(self) -> None:
        tx_id = self._held_transaction()
        dispute = self.svc.open_dispute(tx_id, "owner.acme", "partial delivery")
        self.svc.resolve_dispute(dispute.dispute_id, "split", "arbiter.alpha", provider_amount=30)
        self.assertEqual(self.ledger.balance_of("agent.worker"), 30)
        self.assertEqual(self.ledger.balance_of("owner.acme"), 970)
        self.assertTrue(self.ledger.verify_zero_sum())

    def test_double_resolution_rejected(self) -> None:
        tx_id = self._held_transaction()
        dispute = self.svc.open_dispute(tx_id, "owner.acme", "x")
        self.svc.resolve_dispute(dispute.dispute_id, "refund", "arbiter.alpha")
        with self.assertRaises(ProtocolError):
            self.svc.resolve_dispute(dispute.dispute_id, "slash", "arbiter.alpha")


class ReputationTests(unittest.TestCase):
    def test_score_dynamics(self) -> None:
        engine = ReputationEngine()
        self.assertEqual(engine.score_of("agent.new"), 50.0)
        for _ in range(10):
            engine.on_settled("agent.good", amount=10)
        self.assertEqual(engine.score_of("agent.good"), 70.0)
        engine.on_slashed("agent.bad")
        self.assertEqual(engine.score_of("agent.bad"), 35.0)

    def test_rank_providers_orders_by_score(self) -> None:
        registry = AgentRegistry()
        for agent_id in ["agent.a", "agent.b"]:
            provider = ProviderAgent(agent_id)

            @provider.capability("summarize.pdf", price=10)
            def handler(payload: object) -> object:  # pragma: no cover
                return payload

            registry.register(provider.agent_info())

        engine = ReputationEngine()
        for _ in range(5):
            engine.on_settled("agent.b")
        ranked = engine.rank_providers(registry, "summarize.pdf")
        self.assertEqual([a.agent_id for a in ranked], ["agent.b", "agent.a"])

    def test_attach_wires_events_automatically(self) -> None:
        ledger = funded_ledger()
        svc = ClearingService(ledger=ledger, fees=FeeSchedule(FeePolicy(bps=0)))
        engine = ReputationEngine()
        engine.attach(svc)
        svc.clear("owner.acme", "buyer.bot", make_quote(price=50), lambda: make_result(amount=50))
        self.assertEqual(engine.record("agent.worker").settled, 1)
        self.assertEqual(engine.record("agent.worker").volume, 50)


class ReceiptSignerTests(unittest.TestCase):
    def test_sign_verify_roundtrip(self) -> None:
        signer = ReceiptSigner("secret")
        receipt = signer.sign({"receipt_id": "r1", "amount": 10})
        self.assertTrue(signer.verify(receipt))
        self.assertFalse(ReceiptSigner("other").verify(receipt))


if __name__ == "__main__":
    unittest.main()
