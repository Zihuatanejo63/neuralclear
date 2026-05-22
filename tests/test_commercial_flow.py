import unittest

from neuralclear import SettlementCredit, SpendingMandate, Transaction
from neuralclear.core import ProtocolError
from server.ledger_store import ReferenceClearingService
from tests.test_protocol import make_mandate


class CommercialFlowTests(unittest.TestCase):
    def _settle_pdf_task(self, service: ReferenceClearingService, task_id: str = "task_commercial"):
        quote = service.request_quote("agent.pdf_summarizer", "summarize.pdf")
        mandate = make_mandate(
            max_per_task=100,
            max_daily=1_000,
            capabilities=["summarize.pdf"],
        )
        mandate = SpendingMandate(
            owner="buyer.research",
            agent="agent.alice.delegate",
            allowed_capabilities=mandate.allowed_capabilities,
            max_per_task=mandate.max_per_task,
            max_daily=mandate.max_daily,
            valid_until=mandate.valid_until,
            requires_human_approval_above=mandate.requires_human_approval_above,
            signature=mandate.signature,
        )
        return service.submit_task(
            task_id=task_id,
            quote_id=str(quote["quote_id"]),
            buyer="buyer.research",
            provider="agent.pdf_summarizer",
            payload={"text": "NeuralClear commercial flow test."},
            mandate=mandate,
        )

    def test_platform_fee_provider_amount_and_total_supply(self):
        service = ReferenceClearingService()

        self._settle_pdf_task(service)

        snapshot = service.balances_snapshot()
        self.assertEqual(snapshot["balances"]["buyer.research"], 945)
        self.assertEqual(snapshot["balances"]["agent.pdf_summarizer"], 50)
        self.assertEqual(snapshot["fee_pool"], 5)
        self.assertEqual(snapshot["total_supply"], 1_000)
        self.assertTrue(service.ledger.verify_zero_sum())

    def test_failed_task_does_not_settle(self):
        service = ReferenceClearingService()
        before = service.balances_snapshot()

        with self.assertRaisesRegex(ProtocolError, "unknown quote"):
            service.submit_task(
                task_id="task_failed",
                quote_id="quote_missing",
                buyer="buyer.research",
                provider="agent.pdf_summarizer",
                payload={"text": "should not settle"},
                mandate=make_mandate(capabilities=["summarize.pdf"]),
            )

        self.assertEqual(service.balances_snapshot(), before)
        self.assertEqual(service.ledger.transactions, [])

    def test_duplicate_task_id_cannot_double_charge(self):
        service = ReferenceClearingService()
        self._settle_pdf_task(service, task_id="task_duplicate")
        after_first = service.balances_snapshot()
        quote = service.request_quote("agent.pdf_summarizer", "summarize.pdf")

        with self.assertRaisesRegex(ProtocolError, "duplicate task_id"):
            service.submit_task(
                task_id="task_duplicate",
                quote_id=str(quote["quote_id"]),
                buyer="buyer.research",
                provider="agent.pdf_summarizer",
                payload={"text": "duplicate"},
                mandate=make_mandate(
                    max_per_task=100,
                    max_daily=1_000,
                    capabilities=["summarize.pdf"],
                ),
            )

        self.assertEqual(service.balances_snapshot(), after_first)

    def test_duplicate_settlement_cannot_double_charge(self):
        service = ReferenceClearingService()
        transaction = Transaction(
            sender="buyer.research",
            receiver="agent.pdf_summarizer",
            amount=SettlementCredit(50, "CC"),
            fee=SettlementCredit(5, "CC"),
            capability="summarize.pdf",
        )
        service.ledger.settle(transaction)
        after_first = service.balances_snapshot()

        with self.assertRaisesRegex(ProtocolError, "already settled"):
            service.ledger.settle(transaction)

        self.assertEqual(service.balances_snapshot(), after_first)

    def test_dispute_does_not_change_balances_or_double_refund(self):
        service = ReferenceClearingService()
        task = self._settle_pdf_task(service)
        transaction_id = str(task["result"]["transaction_id"])
        after_settlement = service.balances_snapshot()

        first = service.open_dispute(transaction_id, "buyer.research", "bad summary")
        second = service.open_dispute(transaction_id, "buyer.research", "bad summary")

        self.assertEqual(first["state"], "DISPUTED")
        self.assertEqual(second["state"], "DISPUTED")
        self.assertEqual(service.balances_snapshot(), after_settlement)
