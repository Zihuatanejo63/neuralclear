from datetime import datetime, timedelta, timezone
import unittest

try:
    from fastapi.testclient import TestClient
    import server.app as app_module
    from server.ledger_store import ReferenceClearingService
except ModuleNotFoundError:  # pragma: no cover - exercised in optional CI job.
    TestClient = None
    app_module = None
    ReferenceClearingService = None


@unittest.skipIf(TestClient is None, "FastAPI/httpx test dependencies are not installed")
class HTTPReferenceServerTests(unittest.TestCase):
    def setUp(self):
        app_module.service = ReferenceClearingService()
        self.client = TestClient(app_module.app)
        self.headers = {"X-NeuralClear-API-Key": "dev_neuralclear_key"}

    def _quote(self):
        response = self.client.post(
            "/neuralclear/quote",
            json={
                "buyer": "buyer.research",
                "provider": "agent.pdf_summarizer",
                "capability": "summarize.pdf",
            },
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _mandate(self, max_per_task=100, max_daily=1_000, valid=True):
        return {
            "owner": "buyer.research",
            "agent": "buyer.research.agent",
            "allowed_capabilities": ["summarize.pdf"],
            "max_per_task": {"amount": max_per_task, "currency": "CC"},
            "max_daily": {"amount": max_daily, "currency": "CC"},
            "valid_until": (
                datetime.now(timezone.utc) + (timedelta(days=1) if valid else -timedelta(days=1))
            ).timestamp(),
            "requires_human_approval_above": {"amount": 500, "currency": "CC"},
            "signature": "ed25519:demo",
        }

    def _submit(self, quote_id, task_id="task_http", mandate=None):
        return self.client.post(
            "/neuralclear/tasks",
            json={
                "task_id": task_id,
                "buyer": "buyer.research",
                "provider": "agent.pdf_summarizer",
                "quote_id": quote_id,
                "payload": {
                    "filename": "test.pdf",
                    "text": "NeuralClear is a clearing protocol prototype.",
                },
                "mandate": mandate or self._mandate(),
            },
            headers=self.headers,
        )

    def test_get_manifest(self):
        response = self.client.get("/.well-known/neuralclear/agent.json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["agent_id"], "agent.pdf_summarizer")

    def test_request_quote(self):
        quote = self._quote()

        self.assertEqual(quote["provider"], "agent.pdf_summarizer")
        self.assertEqual(quote["settlement_price"], {"amount": 50, "currency": "CC"})

    def test_submit_task_get_task_get_receipt_and_settle(self):
        quote = self._quote()
        task = self._submit(quote["quote_id"]).json()
        receipt_id = task["result"]["receipt"]["receipt_id"]

        task_response = self.client.get(f"/neuralclear/tasks/{task['task_id']}")
        receipt_response = self.client.get(f"/neuralclear/receipts/{receipt_id}")
        settlement_response = self.client.post(
            "/neuralclear/settlements",
            json={"transaction_id": task["result"]["transaction_id"]},
        )

        self.assertEqual(task_response.status_code, 200)
        self.assertEqual(receipt_response.status_code, 200)
        self.assertEqual(settlement_response.status_code, 200)
        self.assertEqual(task["state"], "SETTLED")
        self.assertEqual(app_module.service.balances_snapshot()["fee_pool"], 5)

    def test_open_dispute(self):
        quote = self._quote()
        task = self._submit(quote["quote_id"]).json()

        response = self.client.post(
            "/neuralclear/disputes",
            json={
                "transaction_id": task["result"]["transaction_id"],
                "opened_by": "buyer.research",
                "reason": "quality issue",
            },
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "DISPUTED")

    def test_invalid_provider_returns_400(self):
        response = self.client.post(
            "/neuralclear/quote",
            json={"provider": "agent.missing", "capability": "summarize.pdf"},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 400)

    def test_invalid_capability_returns_400(self):
        response = self.client.post(
            "/neuralclear/quote",
            json={"provider": "agent.pdf_summarizer", "capability": "translate.text"},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 400)

    def test_invalid_quote_id_returns_400(self):
        response = self._submit("quote_missing")

        self.assertEqual(response.status_code, 400)

    def test_expired_mandate_returns_400(self):
        quote = self._quote()
        response = self._submit(quote["quote_id"], mandate=self._mandate(valid=False))

        self.assertEqual(response.status_code, 400)

    def test_max_per_task_exceeded_returns_400(self):
        quote = self._quote()
        response = self._submit(quote["quote_id"], mandate=self._mandate(max_per_task=10))

        self.assertEqual(response.status_code, 400)

    def test_max_daily_exceeded_returns_400(self):
        first_quote = self._quote()
        self.assertEqual(self._submit(first_quote["quote_id"], task_id="task_one").status_code, 200)
        second_quote = self._quote()

        response = self._submit(
            second_quote["quote_id"],
            task_id="task_two",
            mandate=self._mandate(max_daily=55),
        )

        self.assertEqual(response.status_code, 400)

    def test_insufficient_balance_returns_400(self):
        app_module.service.ledger.balances["buyer.research"] = 10
        quote = self._quote()

        response = self._submit(quote["quote_id"])

        self.assertEqual(response.status_code, 400)

    def test_unknown_task_receipt_and_transaction_return_400(self):
        task_response = self.client.get("/neuralclear/tasks/task_missing")
        receipt_response = self.client.get("/neuralclear/receipts/receipt_missing")
        dispute_response = self.client.post(
            "/neuralclear/disputes",
            json={"transaction_id": "tx_missing", "opened_by": "buyer.research"},
            headers=self.headers,
        )

        self.assertEqual(task_response.status_code, 400)
        self.assertEqual(receipt_response.status_code, 400)
        self.assertEqual(dispute_response.status_code, 400)

    def test_zero_sum_after_http_flow(self):
        quote = self._quote()
        self.assertEqual(self._submit(quote["quote_id"]).status_code, 200)

        self.assertTrue(app_module.service.ledger.verify_zero_sum())
        self.assertEqual(app_module.service.balances_snapshot()["total_supply"], 1_000)
