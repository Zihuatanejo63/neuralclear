"""Tests for the real clearing loop: HTTP wire, net settlement, persistence."""

from __future__ import annotations

import os
import tempfile
import unittest

from neuralclear.buyer import BuyerAgent
from neuralclear.clearing import ClearingService, EscrowLedger, FeePolicy, FeeSchedule
from neuralclear.core import AgentRegistry, ProtocolError, SettlementCredit
from neuralclear.httpwire import ProviderHTTPServer, RemoteProvider
from neuralclear.netting import GENESIS_HASH, ChannelState, NettingService
from neuralclear.provider import ProviderAgent
from neuralclear.store import ClearingStore


def build_provider(agent_id: str = "agent.echo", price: int = 10) -> ProviderAgent:
    provider = ProviderAgent(agent_id, endpoint="http://test")

    @provider.capability("echo.text", price=price, resource_estimate=10, resource_unit="calls")
    def echo(payload: object) -> object:
        return {"echo": payload}

    return provider


class HttpWireTests(unittest.TestCase):
    """Real sockets: provider in a thread, buyer over urllib."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ProviderHTTPServer(build_provider()).start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()

    def test_manifest_roundtrip(self) -> None:
        remote = RemoteProvider(self.server.url)
        info = remote.agent_info()
        self.assertEqual(info.agent_id, "agent.echo")
        self.assertEqual(info.capabilities[0].name, "echo.text")
        self.assertEqual(info.capabilities[0].settlement_price.amount, 10)

    def test_quote_and_task_over_http(self) -> None:
        remote = RemoteProvider(self.server.url)
        quote = remote.handle_quote("echo.text")
        self.assertEqual(quote.provider, "agent.echo")
        self.assertEqual(quote.settlement_price.amount, 10)
        result = remote.handle_task(quote, {"msg": "hello"})
        self.assertEqual(result.output, {"echo": {"msg": "hello"}})

    def test_unknown_capability_maps_to_protocol_error(self) -> None:
        remote = RemoteProvider(self.server.url)
        with self.assertRaises(ProtocolError):
            remote.handle_quote("does.not.exist")

    def test_buyer_purchase_through_real_http(self) -> None:
        registry = AgentRegistry()
        ledger = EscrowLedger()
        ledger.open_account("owner.acme", SettlementCredit(100))
        ledger.open_account("agent.echo", SettlementCredit(0))
        buyer = BuyerAgent("buyer.bot", registry=registry, ledger=ledger, owner="owner.acme")
        agent_id = buyer.connect_remote(self.server.url)
        self.assertEqual(agent_id, "agent.echo")
        outcome = buyer.purchase("echo.text", payload={"msg": "over the wire"})
        self.assertEqual(outcome.result.output, {"echo": {"msg": "over the wire"}})
        self.assertEqual(ledger.balance_of("agent.echo"), 10)
        self.assertTrue(ledger.verify_zero_sum())


class NettingTests(unittest.TestCase):
    def setUp(self) -> None:
        ledger = EscrowLedger()
        ledger.open_account("owner.acme", SettlementCredit(1000))
        ledger.open_account("agent.micro", SettlementCredit(0))
        self.clearing = ClearingService(
            ledger=ledger, fees=FeeSchedule(FeePolicy(bps=0, minimum=2))
        )
        self.netting = NettingService(self.clearing)

    def test_open_meter_settle_math(self) -> None:
        channel = self.netting.open_channel("owner.acme", "agent.micro", deposit=102)
        self.assertEqual(self.clearing.ledger.balance_of("owner.acme"), 898)
        for index in range(50):
            channel.meter("echo.text", 1, payload_hash=f"sha256:{index}")
        receipt = self.netting.settle(channel.channel_id)
        ledger = self.clearing.ledger
        self.assertEqual(ledger.balance_of("agent.micro"), 50)
        self.assertEqual(ledger.balance_of("owner.acme"), 948)  # 898 + 50 unused back
        self.assertEqual(ledger.fee_pool, 2)
        self.assertEqual(receipt["tasks_metered"], 50)
        self.assertEqual(receipt["net_to_provider"], 50)
        self.assertEqual(receipt["refunded_to_buyer"], 50)
        self.assertTrue(self.clearing.signer.verify(receipt))
        self.assertTrue(ledger.verify_zero_sum())
        self.assertIs(channel.state, ChannelState.SETTLED)

    def test_hash_chain_links_and_tamper_detection(self) -> None:
        channel = self.netting.open_channel("owner.acme", "agent.micro", deposit=20)
        first = channel.meter("echo.text", 1, "sha256:a")
        second = channel.meter("echo.text", 1, "sha256:b")
        self.assertEqual(first.prev_hash, GENESIS_HASH)
        self.assertEqual(second.prev_hash, first.record_hash())
        self.assertTrue(channel.verify_chain())
        # tamper: replace a record with a forged amount
        forged = type(first)(
            sequence=0,
            capability="echo.text",
            amount=999,
            payload_hash="sha256:a",
            prev_hash=GENESIS_HASH,
            recorded_at=first.recorded_at,
        )
        channel.records[0] = forged
        self.assertFalse(channel.verify_chain())
        with self.assertRaises(ProtocolError):
            self.netting.settle(channel.channel_id)

    def test_meter_cannot_exceed_deposit(self) -> None:
        channel = self.netting.open_channel("owner.acme", "agent.micro", deposit=5)
        for _ in range(channel.spendable()):
            channel.meter("echo.text", 1, "sha256:x")
        with self.assertRaises(ProtocolError):
            channel.meter("echo.text", 1, "sha256:y")

    def test_disputed_channel_freezes_and_refunds(self) -> None:
        channel = self.netting.open_channel("owner.acme", "agent.micro", deposit=50)
        channel.meter("echo.text", 1, "sha256:a")
        self.netting.dispute(channel.channel_id)
        with self.assertRaises(ProtocolError):
            channel.meter("echo.text", 1, "sha256:b")
        dispute = self.clearing.open_dispute(
            channel.transaction.transaction_id, "owner.acme", "provider offline mid-channel"
        )
        self.clearing.resolve_dispute(dispute.dispute_id, "refund", "arbiter.alpha")
        self.assertEqual(self.clearing.ledger.balance_of("owner.acme"), 1000)
        self.assertTrue(self.clearing.ledger.verify_zero_sum())

    def test_savings_analytics(self) -> None:
        channel = self.netting.open_channel("owner.acme", "agent.micro", deposit=102)
        for _ in range(100):
            channel.meter("echo.text", 1, "sha256:x")
        stats = self.netting.settlement_savings(channel.channel_id, per_settlement_cost=0.001)
        self.assertEqual(stats["settlements_avoided"], 99)
        self.assertEqual(stats["cost_reduction_factor"], 100)


class PersistenceTests(unittest.TestCase):
    def test_save_load_roundtrip_preserves_money(self) -> None:
        ledger = EscrowLedger()
        ledger.open_account("owner.acme", SettlementCredit(500))
        ledger.open_account("agent.worker", SettlementCredit(0))
        service = ClearingService(ledger=ledger, fees=FeeSchedule(FeePolicy(minimum=1)))

        from neuralclear.core import MockProof, ResourceUnit, TaskResult
        from neuralclear.core import Quote

        quote = Quote(
            provider="agent.worker",
            capability="echo.text",
            resource_estimate=ResourceUnit(1, "calls"),
            settlement_price=SettlementCredit(40),
            expires_at=float("inf"),
        )
        service.clear(
            "owner.acme",
            "buyer.bot",
            quote,
            lambda: TaskResult("", {"ok": True}, [ResourceUnit(1, "calls")], SettlementCredit(40), MockProof()),
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "clearing.db")
            ClearingStore(path).save(service)

            restored = ClearingStore(path).load()
            self.assertEqual(restored.ledger.balance_of("owner.acme"), 459)
            self.assertEqual(restored.ledger.balance_of("agent.worker"), 40)
            self.assertEqual(restored.ledger.fee_pool, 1)
            self.assertEqual(restored.ledger.total_supply, 500)
            self.assertTrue(restored.ledger.verify_zero_sum())
            self.assertEqual(len(restored.receipts), 1)
            receipt = next(iter(restored.receipts.values()))
            self.assertTrue(service.signer.verify(receipt))  # signature survives disk


if __name__ == "__main__":
    unittest.main()
