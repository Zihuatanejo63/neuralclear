import unittest

from server.ledger_store import ReferenceClearingService
from server.signing import result_hash, verify_receipt
from tests.test_v03_sandbox import pdf_mandate


class SignedReceiptTests(unittest.TestCase):
    def _settled_task(self):
        service = ReferenceClearingService()
        quote = service.request_quote("agent.pdf_summarizer", "summarize.pdf")
        task = service.submit_task(
            task_id="task_signed_receipt",
            quote_id=str(quote["quote_id"]),
            buyer="buyer.research",
            provider="agent.pdf_summarizer",
            payload={"text": "Signed receipt test."},
            mandate=pdf_mandate(),
        )
        return task

    def test_signed_receipt_verifies(self):
        task = self._settled_task()
        receipt = task["result"]["receipt"]

        self.assertTrue(verify_receipt(receipt))

    def test_signed_receipt_fails_if_amount_modified(self):
        task = self._settled_task()
        receipt = dict(task["result"]["receipt"])
        receipt["amount"] = 51

        self.assertFalse(verify_receipt(receipt))

    def test_signed_receipt_fails_if_provider_modified(self):
        task = self._settled_task()
        receipt = dict(task["result"]["receipt"])
        receipt["provider"] = "agent.attacker"

        self.assertFalse(verify_receipt(receipt))

    def test_task_result_hash_is_bound_to_receipt(self):
        task = self._settled_task()
        result_without_receipt = {
            key: value for key, value in task["result"].items() if key != "receipt"
        }

        self.assertEqual(
            task["result"]["receipt"]["result_hash"],
            result_hash(result_without_receipt),
        )
