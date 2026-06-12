"""Tests for the ten-line Provider/Buyer SDK (neuralclear.provider / neuralclear.buyer)."""

from __future__ import annotations

import unittest

from neuralclear.buyer import BuyerAgent
from neuralclear.core import (
    AgentRegistry,
    Ledger,
    ProtocolError,
    SettlementCredit,
    SpendingMandate,
)
from neuralclear.provider import ProviderAgent


def build_provider() -> ProviderAgent:
    provider = ProviderAgent("agent.summarizer", endpoint="https://example.com")

    @provider.capability("summarize.pdf", price=25, resource_estimate=8000, resource_unit="tokens")
    def summarize(payload: object) -> object:
        text = payload.get("text", "") if isinstance(payload, dict) else str(payload)
        return {"summary": text[:16]}

    return provider


def build_mandate(max_per_task: int = 100, max_daily: int = 1000) -> SpendingMandate:
    return SpendingMandate(
        owner="owner.acme",
        agent="buyer.bot",
        allowed_capabilities=["summarize.pdf"],
        max_per_task=SettlementCredit(max_per_task),
        max_daily=SettlementCredit(max_daily),
        valid_until=float("inf"),
        requires_human_approval_above=SettlementCredit(max_per_task),
        signature="ed25519:test",
    )


class ProviderAgentTests(unittest.TestCase):
    def test_manifest_lists_capability_and_pricing(self) -> None:
        provider = build_provider()
        manifest = provider.manifest()
        self.assertEqual(manifest["agent_id"], "agent.summarizer")
        caps = manifest["capabilities"]
        self.assertEqual(len(caps), 1)
        self.assertEqual(caps[0]["name"], "summarize.pdf")
        self.assertEqual(caps[0]["settlement_price"]["amount"], 25)

    def test_quote_then_task_executes_handler(self) -> None:
        provider = build_provider()
        quote = provider.handle_quote("summarize.pdf")
        result = provider.handle_task(quote, {"text": "agent to agent clearing"})
        self.assertEqual(result.output, {"summary": "agent to agent c"})
        self.assertEqual(result.settlement_amount.amount, 25)

    def test_unknown_capability_rejected(self) -> None:
        provider = build_provider()
        with self.assertRaises(ProtocolError):
            provider.handle_quote("translate.text")

    def test_nonpositive_price_rejected(self) -> None:
        provider = ProviderAgent("agent.bad")
        with self.assertRaises(ProtocolError):

            @provider.capability("free.lunch", price=0)
            def handler(payload: object) -> object:  # pragma: no cover
                return payload


class BuyerAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = build_provider()
        self.registry = AgentRegistry()
        self.ledger = Ledger()
        self.ledger.open_account("owner.acme", SettlementCredit(200))
        self.ledger.open_account("agent.summarizer", SettlementCredit(0))
        self.buyer = BuyerAgent(
            "buyer.bot",
            registry=self.registry,
            ledger=self.ledger,
            mandate=build_mandate(),
            owner="owner.acme",
        )
        self.buyer.connect_local(self.provider)

    def test_purchase_settles_and_returns_receipt(self) -> None:
        outcome = self.buyer.purchase("summarize.pdf", payload={"text": "hello world, agents"})
        self.assertEqual(outcome.transaction.state.value, "SETTLED")
        self.assertEqual(self.ledger.balance_of("owner.acme"), 175)
        self.assertEqual(self.ledger.balance_of("agent.summarizer"), 25)
        self.assertTrue(outcome.receipt["receipt_id"].startswith("rcpt_tx_"))
        self.assertTrue(self.ledger.verify_zero_sum())

    def test_purchase_discovers_provider_when_not_named(self) -> None:
        outcome = self.buyer.purchase("summarize.pdf", payload={"text": "x"})
        self.assertEqual(outcome.transaction.receiver, "agent.summarizer")

    def test_mandate_blocks_disallowed_capability(self) -> None:
        provider2 = ProviderAgent("agent.coder")

        @provider2.capability("review.code", price=10)
        def review(payload: object) -> object:  # pragma: no cover
            return {"ok": True}

        self.buyer.connect_local(provider2)
        with self.assertRaises(ProtocolError):
            self.buyer.purchase("review.code", payload={})

    def test_mandate_blocks_over_budget_task(self) -> None:
        expensive = ProviderAgent("agent.gpu")

        @expensive.capability("train.model", price=500)
        def train(payload: object) -> object:  # pragma: no cover
            return {"ok": True}

        buyer = BuyerAgent(
            "buyer.bot",
            registry=self.registry,
            ledger=self.ledger,
            mandate=SpendingMandate(
                owner="owner.acme",
                agent="buyer.bot",
                allowed_capabilities=["train.model"],
                max_per_task=SettlementCredit(100),
                max_daily=SettlementCredit(1000),
                valid_until=float("inf"),
                requires_human_approval_above=SettlementCredit(100),
                signature="ed25519:test",
            ),
            owner="owner.acme",
        )
        buyer.connect_local(expensive)
        with self.assertRaises(ProtocolError):
            buyer.purchase("train.model", payload={})

    def test_insufficient_credit_blocks_settlement(self) -> None:
        poor_ledger = Ledger()
        poor_ledger.open_account("owner.broke", SettlementCredit(5))
        poor_ledger.open_account("agent.summarizer", SettlementCredit(0))
        buyer = BuyerAgent(
            "buyer.bot",
            registry=AgentRegistry(),
            ledger=poor_ledger,
            owner="owner.broke",
        )
        buyer.connect_local(build_provider())
        with self.assertRaises(ProtocolError):
            buyer.purchase("summarize.pdf", payload={"text": "x"})

    def test_no_provider_found(self) -> None:
        with self.assertRaises(ProtocolError):
            self.buyer.purchase("does.not.exist", payload={})


if __name__ == "__main__":
    unittest.main()
