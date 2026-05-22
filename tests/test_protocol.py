from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import unittest

from neuralclear import (
    AgentInfo,
    AgentRegistry,
    Capability,
    Ledger,
    MockProof,
    NeuralClearSDK,
    ProofLevel,
    Quote,
    ResourceUnit,
    SettlementCredit,
    SpendingMandate,
    Transaction,
    TransactionState,
)
from neuralclear.core import ProtocolError


ROOT = Path(__file__).resolve().parents[1]


def make_agent(agent_id="agent.researcher", price=25) -> AgentInfo:
    return AgentInfo(
        agent_id=agent_id,
        name="Research Agent",
        endpoint="https://research.example.com/a2a",
        public_key="did:key:zExamplePublicKey",
        capabilities=[
            Capability(
                name="summarize.paper",
                resource_price=ResourceUnit(8000, "tokens"),
                settlement_price=SettlementCredit(price),
            )
        ],
        reputation_score=0.9,
    )


def make_sdk(alice_balance=100, provider_balance=0, price=25):
    registry = AgentRegistry()
    agent = make_agent(price=price)
    registry.register(agent)
    ledger = Ledger()
    ledger.open_account("user.alice", SettlementCredit(alice_balance))
    ledger.open_account(agent.agent_id, SettlementCredit(provider_balance))
    return NeuralClearSDK(registry, ledger), ledger, agent


def make_mandate(max_per_task=30, max_daily=100, capabilities=None) -> SpendingMandate:
    return SpendingMandate(
        owner="user.alice",
        agent="agent.alice.delegate",
        allowed_capabilities=capabilities or ["summarize.paper"],
        max_per_task=SettlementCredit(max_per_task),
        max_daily=SettlementCredit(max_daily),
        valid_until=(datetime.now(timezone.utc) + timedelta(days=1)).timestamp(),
        requires_human_approval_above=SettlementCredit(50),
        signature="ed25519:demo",
    )


class ProtocolTests(unittest.TestCase):
    def test_payment_direction(self):
        sdk, ledger, agent = make_sdk()
        quote = sdk.request_quote(agent.agent_id, "summarize.paper")

        sdk.call("user.alice", agent.agent_id, quote, {"url": "https://example.com"}, make_mandate())

        self.assertEqual(ledger.balance_of("user.alice"), 75)
        self.assertEqual(ledger.balance_of(agent.agent_id), 25)
        self.assertEqual(ledger.transactions[-1].amount.amount, 25)

    def test_insufficient_credit(self):
        sdk, _, agent = make_sdk(alice_balance=10)
        quote = sdk.request_quote(agent.agent_id, "summarize.paper")

        with self.assertRaisesRegex(ProtocolError, "insufficient credit"):
            sdk.call("user.alice", agent.agent_id, quote, {}, make_mandate())

    def test_zero_sum(self):
        _, ledger, agent = make_sdk()
        tx = Transaction(
            sender="user.alice",
            receiver=agent.agent_id,
            amount=SettlementCredit(25),
            fee=SettlementCredit(2),
            capability="summarize.paper",
        )
        before = ledger.snapshot()

        ledger.settle(tx)

        self.assertTrue(ledger.verify_zero_sum(before))
        self.assertTrue(ledger.verify_zero_sum())
        self.assertTrue(ledger.verify_transaction_zero_sum(before, tx))
        self.assertEqual(ledger.balance_of("user.alice"), 73)
        self.assertEqual(ledger.balance_of(agent.agent_id), 25)
        self.assertEqual(ledger.fee_pool, 2)

    def test_agent_registration(self):
        registry = AgentRegistry()
        agent = make_agent()

        registry.register(agent)

        self.assertIs(registry.get(agent.agent_id), agent)
        with self.assertRaisesRegex(ProtocolError, "already registered"):
            registry.register(agent)

    def test_discover_capability(self):
        registry = AgentRegistry()
        registry.register(make_agent("agent.researcher"))
        registry.register(make_agent("agent.writer"))

        matches = registry.discover("summarize.paper")

        self.assertEqual([agent.agent_id for agent in matches], ["agent.researcher", "agent.writer"])

    def test_mandate_limit(self):
        sdk, _, agent = make_sdk(price=50)
        quote = sdk.request_quote(agent.agent_id, "summarize.paper")

        with self.assertRaisesRegex(ProtocolError, "max_per_task"):
            sdk.call("user.alice", agent.agent_id, quote, {}, make_mandate(max_per_task=30))

    def test_mandate_daily_limit(self):
        sdk, _, agent = make_sdk(alice_balance=100, price=25)
        mandate = make_mandate(max_per_task=30, max_daily=40)

        first_quote = sdk.request_quote(agent.agent_id, "summarize.paper")
        sdk.call("user.alice", agent.agent_id, first_quote, {}, mandate)

        second_quote = sdk.request_quote(agent.agent_id, "summarize.paper")
        with self.assertRaisesRegex(ProtocolError, "max_daily"):
            sdk.call(
                "user.alice",
                agent.agent_id,
                second_quote,
                {},
                mandate,
            )

    def test_quote_expiration(self):
        sdk, _, agent = make_sdk()
        expired_quote = Quote(
            provider=agent.agent_id,
            capability="summarize.paper",
            resource_estimate=ResourceUnit(8000, "tokens"),
            settlement_price=SettlementCredit(25),
            expires_at=(datetime.now(timezone.utc) - timedelta(seconds=1)).timestamp(),
        )

        with self.assertRaisesRegex(ProtocolError, "quote expired"):
            sdk.call("user.alice", agent.agent_id, expired_quote, {}, make_mandate())

    def test_dispute_state(self):
        tx = Transaction(
            sender="user.alice",
            receiver="agent.researcher",
            amount=SettlementCredit(25),
            capability="summarize.paper",
            state=TransactionState.TASK_RUNNING,
        )

        tx.transition(TransactionState.DISPUTED)
        tx.transition(TransactionState.REFUNDED)

        self.assertEqual(tx.state, TransactionState.REFUNDED)

    def test_mock_proof_is_not_real_attestation(self):
        self.assertTrue(MockProof().verify())
        self.assertFalse(MockProof(proof_level=ProofLevel.SIGNED_RESULT).verify())
        self.assertFalse(MockProof(proof_level=ProofLevel.REPRODUCIBLE).verify())
        self.assertFalse(MockProof(proof_level=ProofLevel.TEE_ATTESTATION).verify())

    def test_settled_transaction_cannot_be_refunded_without_dispute_resolution_policy(self):
        _, ledger, agent = make_sdk()
        tx = Transaction(
            sender="user.alice",
            receiver=agent.agent_id,
            amount=SettlementCredit(25),
            capability="summarize.paper",
        )
        ledger.settle(tx)

        with self.assertRaisesRegex(ProtocolError, "invalid transition"):
            ledger.refund(tx)

    def test_spec_file_exists(self):
        spec = ROOT / "SPEC.md"

        self.assertTrue(spec.exists())
        content = spec.read_text(encoding="utf-8")
        self.assertIn("Protocol Objects", content)
        self.assertIn("Transaction Direction", content)
        self.assertIn("Non-Goals", content)

    def test_examples_can_be_loaded(self):
        example_paths = [
            ROOT / "examples" / "agent_manifest.json",
            ROOT / "examples" / "quote.json",
            ROOT / "examples" / "spending_mandate.json",
            ROOT / "examples" / "task_result.json",
            ROOT / "examples" / "transaction.json",
            ROOT / "examples" / "well-known" / "agent.json",
            ROOT / "schemas" / "agent_manifest.schema.json",
        ]

        for path in example_paths:
            with self.subTest(path=path):
                self.assertTrue(path.exists())
                json.loads(path.read_text(encoding="utf-8"))
