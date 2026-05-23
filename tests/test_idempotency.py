from pathlib import Path
import tempfile
import unittest

from neuralclear.core import ProtocolError
from server.ledger_store import ReferenceClearingService
from tests.test_v03_sandbox import pdf_mandate


class IdempotencyTests(unittest.TestCase):
    def _quote(self, service: ReferenceClearingService):
        return service.request_quote("agent.pdf_summarizer", "summarize.pdf")

    def _submit(
        self,
        service: ReferenceClearingService,
        quote_id: str,
        payload: dict[str, object] | None = None,
    ):
        return service.submit_task(
            task_id="task_idempotent",
            quote_id=quote_id,
            buyer="buyer.research",
            provider="agent.pdf_summarizer",
            payload=payload or {"text": "Idempotent task."},
            mandate=pdf_mandate(),
            idempotency_key="idem_123",
        )

    def test_idempotency_key_prevents_double_charge(self):
        service = ReferenceClearingService()
        quote = self._quote(service)

        self._submit(service, str(quote["quote_id"]))
        self._submit(service, str(quote["quote_id"]))

        self.assertEqual(service.balances_snapshot()["balances"]["buyer.research"], 945)
        self.assertEqual(len(service.ledger.transactions), 1)

    def test_idempotency_key_returns_same_receipt(self):
        service = ReferenceClearingService()
        quote = self._quote(service)

        first = self._submit(service, str(quote["quote_id"]))
        second = self._submit(service, str(quote["quote_id"]))

        self.assertEqual(
            first["result"]["receipt"]["receipt_id"],
            second["result"]["receipt"]["receipt_id"],
        )

    def test_idempotency_key_conflicting_payload_returns_409(self):
        service = ReferenceClearingService()
        quote = self._quote(service)
        self._submit(service, str(quote["quote_id"]), {"text": "first"})

        with self.assertRaisesRegex(ProtocolError, "idempotency key conflict"):
            self._submit(service, str(quote["quote_id"]), {"text": "second"})

    def test_idempotency_survives_storage_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "neuralclear.db")
            first_service = ReferenceClearingService(storage_path=db_path)
            quote = self._quote(first_service)
            first = self._submit(first_service, str(quote["quote_id"]))
            first_service.close()

            restarted = ReferenceClearingService(storage_path=db_path)
            try:
                second = self._submit(restarted, str(quote["quote_id"]))
                self.assertEqual(
                    first["result"]["receipt"]["receipt_id"],
                    second["result"]["receipt"]["receipt_id"],
                )
                self.assertEqual(
                    restarted.balances_snapshot()["balances"]["buyer.research"],
                    945,
                )
            finally:
                restarted.close()
