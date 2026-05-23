from pathlib import Path
import unittest
from unittest.mock import patch

from client import cli
from server.registry_store import build_default_registry_store

try:
    from fastapi.testclient import TestClient
    import server.app as app_module
    from server.ledger_store import ReferenceClearingService
except ModuleNotFoundError:  # pragma: no cover - exercised when HTTP deps are absent.
    TestClient = None
    app_module = None
    ReferenceClearingService = None


ROOT = Path(__file__).resolve().parents[1]
API_KEY = "dev_neuralclear_key"
READ_KEY = "dev_neuralclear_read_key"


@unittest.skipIf(TestClient is None, "FastAPI/httpx test dependencies are not installed")
class APIKeyAuthTests(unittest.TestCase):
    def setUp(self):
        app_module.service = ReferenceClearingService()
        self.client = TestClient(app_module.app)

    def test_missing_api_key_rejected(self):
        response = self.client.post(
            "/neuralclear/quote",
            json={"provider": "agent.pdf_summarizer", "capability": "summarize.pdf"},
        )

        self.assertEqual(response.status_code, 401)

    def test_invalid_api_key_rejected(self):
        response = self.client.post(
            "/neuralclear/quote",
            json={"provider": "agent.pdf_summarizer", "capability": "summarize.pdf"},
            headers={"X-NeuralClear-API-Key": "wrong"},
        )

        self.assertEqual(response.status_code, 401)

    def test_valid_write_key_allows_task(self):
        headers = {"X-NeuralClear-API-Key": API_KEY}
        quote = self.client.post(
            "/neuralclear/quote",
            json={"provider": "agent.pdf_summarizer", "capability": "summarize.pdf"},
            headers=headers,
        )
        task = self.client.post(
            "/neuralclear/tasks",
            json={
                "buyer": "buyer.research",
                "provider": "agent.pdf_summarizer",
                "quote_id": quote.json()["quote_id"],
                "payload": {"text": "V0.4 authorized task."},
            },
            headers=headers,
        )

        self.assertEqual(quote.status_code, 200)
        self.assertEqual(task.status_code, 200)
        self.assertEqual(task.json()["state"], "SETTLED")

    def test_read_only_key_cannot_submit_task(self):
        response = self.client.post(
            "/neuralclear/quote",
            json={"provider": "agent.pdf_summarizer", "capability": "summarize.pdf"},
            headers={"X-NeuralClear-API-Key": READ_KEY},
        )

        self.assertEqual(response.status_code, 403)

    def test_read_only_key_can_access_registry(self):
        response = self.client.get(
            "/registry/agents",
            headers={"X-NeuralClear-API-Key": READ_KEY},
        )

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()), 1)


class V04DeveloperPreviewTests(unittest.TestCase):
    def test_cli_remote_base_url_and_api_key(self):
        with patch.dict(
            "os.environ",
            {
                "NEURALCLEAR_BASE_URL": "https://sandbox.example.test",
                "NEURALCLEAR_API_KEY": "dev_test_key",
            },
        ):
            with patch("client.cli.NeuralClearHTTPClient") as client_type:
                client_type.return_value.list_agents.return_value = []
                code = cli.main(["agents", "list"])

        self.assertEqual(code, 0)
        client_type.assert_called_once_with("https://sandbox.example.test", api_key="dev_test_key")

    def test_cli_uses_api_key_for_write_endpoints(self):
        with patch("client.cli.NeuralClearHTTPClient") as client_type:
            client = client_type.return_value
            client.request_quote.return_value = {"quote_id": "quote_cli"}

            code = cli.main(
                [
                    "--api-key",
                    "write_cli_key",
                    "quote",
                    "request",
                    "agent.pdf_summarizer",
                    "summarize.pdf",
                ]
            )

        self.assertEqual(code, 0)
        client_type.assert_called_once_with("http://127.0.0.1:8000", api_key="write_cli_key")
        client.request_quote.assert_called_once()

    def test_docker_files_exist(self):
        for path in ["Dockerfile", "docker-compose.yml", ".env.example"]:
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).exists())

    def test_seed_agents_loaded(self):
        store = build_default_registry_store()
        agent_ids = {agent["agent_id"] for agent in store.list_agents()}

        self.assertIn("agent.pdf_summarizer", agent_ids)
        self.assertIn("agent.web_search", agent_ids)
        self.assertIn("agent.code_review", agent_ids)

    def test_python_files_are_multiline(self):
        checked = [
            ROOT / "server" / "app.py",
            ROOT / "server" / "storage.py",
            ROOT / "client" / "cli.py",
            ROOT / "server" / "registry_store.py",
            ROOT / "server" / "dashboard.py",
        ]
        for path in checked:
            with self.subTest(path=path.name):
                self.assertGreater(len(path.read_text(encoding="utf-8").splitlines()), 20)


@unittest.skipIf(TestClient is None, "FastAPI/httpx test dependencies are not installed")
class V04SandboxFlowTests(unittest.TestCase):
    def setUp(self):
        app_module.service = ReferenceClearingService()
        self.client = TestClient(app_module.app)
        self.headers = {"X-NeuralClear-API-Key": API_KEY}

    def test_dashboard_with_seed_data(self):
        response = self.client.get("/dashboard/agents")

        self.assertEqual(response.status_code, 200)
        self.assertIn("PDF Summarizer Agent", response.text)
        self.assertIn("Web Search Agent", response.text)
        self.assertIn("Code Review Agent", response.text)

    def test_remote_sandbox_flow(self):
        quote = self.client.post(
            "/neuralclear/quote",
            json={"provider": "agent.pdf_summarizer", "capability": "summarize.pdf"},
            headers=self.headers,
        )
        task = self.client.post(
            "/neuralclear/tasks",
            json={
                "buyer": "buyer.research",
                "provider": "agent.pdf_summarizer",
                "quote_id": quote.json()["quote_id"],
                "payload": {"text": "Hosted sandbox developer preview flow."},
            },
            headers=self.headers,
        )
        receipt_id = task.json()["result"]["receipt"]["receipt_id"]
        receipt = self.client.get(f"/neuralclear/receipts/{receipt_id}")
        balances = self.client.get("/neuralclear/balances")

        self.assertEqual(quote.status_code, 200)
        self.assertEqual(task.status_code, 200)
        self.assertEqual(receipt.status_code, 200)
        self.assertEqual(balances.json()["balances"]["buyer.research"], 945)
        self.assertEqual(balances.json()["fee_pool"], 5)

    def test_idempotency_key_prevents_double_charge(self):
        quote = self.client.post(
            "/neuralclear/quote",
            json={"provider": "agent.pdf_summarizer", "capability": "summarize.pdf"},
            headers=self.headers,
        )
        body = {
            "buyer": "buyer.research",
            "provider": "agent.pdf_summarizer",
            "quote_id": quote.json()["quote_id"],
            "payload": {"text": "HTTP idempotency."},
        }
        headers = {**self.headers, "Idempotency-Key": "http_idem_1"}

        first = self.client.post("/neuralclear/tasks", json=body, headers=headers)
        second = self.client.post("/neuralclear/tasks", json=body, headers=headers)
        balances = self.client.get("/neuralclear/balances")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(balances.json()["balances"]["buyer.research"], 945)
        self.assertEqual(len(app_module.service.ledger.transactions), 1)

    def test_idempotency_key_returns_same_receipt(self):
        quote = self.client.post(
            "/neuralclear/quote",
            json={"provider": "agent.pdf_summarizer", "capability": "summarize.pdf"},
            headers=self.headers,
        )
        body = {
            "buyer": "buyer.research",
            "provider": "agent.pdf_summarizer",
            "quote_id": quote.json()["quote_id"],
            "payload": {"text": "Same receipt."},
        }
        headers = {**self.headers, "Idempotency-Key": "http_idem_2"}

        first = self.client.post("/neuralclear/tasks", json=body, headers=headers)
        second = self.client.post("/neuralclear/tasks", json=body, headers=headers)

        self.assertEqual(
            first.json()["result"]["receipt"]["receipt_id"],
            second.json()["result"]["receipt"]["receipt_id"],
        )

    def test_idempotency_key_conflicting_payload_returns_409(self):
        quote = self.client.post(
            "/neuralclear/quote",
            json={"provider": "agent.pdf_summarizer", "capability": "summarize.pdf"},
            headers=self.headers,
        )
        body = {
            "buyer": "buyer.research",
            "provider": "agent.pdf_summarizer",
            "quote_id": quote.json()["quote_id"],
            "payload": {"text": "first"},
        }
        headers = {**self.headers, "Idempotency-Key": "http_idem_3"}

        first = self.client.post("/neuralclear/tasks", json=body, headers=headers)
        body["payload"] = {"text": "second"}
        second = self.client.post("/neuralclear/tasks", json=body, headers=headers)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
