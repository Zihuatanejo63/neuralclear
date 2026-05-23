from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from client import cli
from client.http_client import NeuralClearHTTPClient
from neuralclear import SettlementCredit, SpendingMandate
from server.ledger_store import ReferenceClearingService
from server.registry_store import AgentRegistryStore

try:
    from fastapi.testclient import TestClient
    import server.app as app_module
except ModuleNotFoundError:  # pragma: no cover - exercised in optional CI job.
    TestClient = None
    app_module = None


def pdf_mandate(max_daily: int = 1_000) -> SpendingMandate:
    return SpendingMandate(
        owner="buyer.research",
        agent="buyer.research.agent",
        allowed_capabilities=["summarize.pdf"],
        max_per_task=SettlementCredit(100, "CC"),
        max_daily=SettlementCredit(max_daily, "CC"),
        valid_until=(datetime.now(timezone.utc) + timedelta(days=1)).timestamp(),
        requires_human_approval_above=SettlementCredit(500, "CC"),
        signature="ed25519:demo",
    )


def registerable_manifest(agent_id: str = "agent.extra") -> dict[str, object]:
    return {
        "agent_id": agent_id,
        "name": "Extra Agent",
        "endpoint": "http://127.0.0.1:9000",
        "public_key": "did:key:zExtra",
        "capabilities": ["summarize.pdf", "translate.text"],
        "pricing": [
            {
                "capability": "summarize.pdf",
                "resource_unit": {"amount": 1, "unit": "request"},
                "settlement_credit": {"amount": 40, "currency": "CC"},
            }
        ],
        "reputation": {"score": 0.8, "completed_tasks": 3, "dispute_rate": 0},
    }


class RegistryStoreTests(unittest.TestCase):
    def test_registry_register_agent(self):
        store = AgentRegistryStore()

        registered = store.register(registerable_manifest())

        self.assertEqual(registered["agent_id"], "agent.extra")
        self.assertEqual(store.get("agent.extra")["name"], "Extra Agent")

    def test_registry_search_by_capability(self):
        store = AgentRegistryStore()
        store.register(registerable_manifest("agent.one"))
        store.register({**registerable_manifest("agent.two"), "capabilities": ["search.web"]})

        matches = store.search("summarize.pdf")

        self.assertEqual([agent["agent_id"] for agent in matches], ["agent.one"])


class SQLitePersistenceTests(unittest.TestCase):
    def _settle_task(self, service: ReferenceClearingService):
        quote = service.request_quote("agent.pdf_summarizer", "summarize.pdf")
        return service.submit_task(
            task_id="task_persistent",
            quote_id=str(quote["quote_id"]),
            buyer="buyer.research",
            provider="agent.pdf_summarizer",
            payload={"text": "Persistent receipt test."},
            mandate=pdf_mandate(),
        )

    def test_sqlite_persistence_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "neuralclear.db")
            first = ReferenceClearingService(storage_path=db_path)
            self._settle_task(first)

            restarted = ReferenceClearingService(storage_path=db_path)
            try:
                self.assertEqual(restarted.balances_snapshot()["balances"]["buyer.research"], 945)
                self.assertEqual(len(restarted.list_receipts()), 1)
                self.assertEqual(len(restarted.ledger.transactions), 1)
            finally:
                first.close()
                restarted.close()

    def test_receipt_is_stable_and_retrievable(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "neuralclear.db")
            first = ReferenceClearingService(storage_path=db_path)
            task = self._settle_task(first)
            receipt_id = task["result"]["receipt"]["receipt_id"]

            restarted = ReferenceClearingService(storage_path=db_path)
            try:
                receipt = restarted.get_receipt(receipt_id)
                self.assertEqual(receipt["receipt_id"], receipt_id)
                self.assertEqual(receipt["amount"], 50)
            finally:
                first.close()
                restarted.close()

    def test_dispute_is_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "neuralclear.db")
            first = ReferenceClearingService(storage_path=db_path)
            task = self._settle_task(first)
            dispute = first.open_dispute(
                task["result"]["transaction_id"], "buyer.research", "quality"
            )

            restarted = ReferenceClearingService(storage_path=db_path)
            try:
                self.assertEqual(restarted.list_disputes()[0]["dispute_id"], dispute["dispute_id"])
            finally:
                first.close()
                restarted.close()

    def test_balance_snapshot_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "neuralclear.db")
            first = ReferenceClearingService(storage_path=db_path)
            self._settle_task(first)

            restarted = ReferenceClearingService(storage_path=db_path)
            try:
                snapshot = restarted.balances_snapshot()
                self.assertEqual(snapshot["balances"]["agent.pdf_summarizer"], 50)
                self.assertEqual(snapshot["fee_pool"], 5)
                self.assertEqual(snapshot["total_supply"], 1_000)
            finally:
                first.close()
                restarted.close()


@unittest.skipIf(TestClient is None, "FastAPI/httpx test dependencies are not installed")
class DashboardAndRegistryHTTPTests(unittest.TestCase):
    def setUp(self):
        app_module.service = ReferenceClearingService()
        self.client = TestClient(app_module.app)
        self.headers = {"X-NeuralClear-API-Key": "dev_neuralclear_key"}

    def test_registry_http_register_and_search(self):
        response = self.client.post(
            "/registry/agents",
            json=registerable_manifest(),
            headers=self.headers,
        )
        search = self.client.get("/registry/search?capability=translate.text")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.json()[0]["agent_id"], "agent.extra")

    def test_dashboard_pages_return_200(self):
        for path in [
            "/dashboard/agents",
            "/dashboard/transactions",
            "/dashboard/receipts",
            "/dashboard/disputes",
            "/dashboard/balances",
        ]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response.headers["content-type"])


class CLITests(unittest.TestCase):
    def test_cli_quote_and_task_flow(self):
        with patch("client.cli.NeuralClearHTTPClient") as client_type:
            client = client_type.return_value
            client.request_quote.return_value = {"quote_id": "quote_cli"}
            client.submit_task.return_value = {"task_id": "task_cli", "state": "SETTLED"}

            quote_code = cli.main(["quote", "request", "agent.pdf_summarizer", "summarize.pdf"])
            task_code = cli.main(["task", "submit", "quote_cli", "--text", "hello"])

        self.assertEqual(quote_code, 0)
        self.assertEqual(task_code, 0)
        client_type.assert_called_with("http://127.0.0.1:8000", api_key=None)
        client.request_quote.assert_called_once()
        client.submit_task.assert_called_once()
        self.assertIsNone(client.submit_task.call_args.kwargs["idempotency_key"])


@unittest.skipIf(TestClient is None, "FastAPI/httpx test dependencies are not installed")
class ProcessE2ETests(unittest.TestCase):
    def test_process_http_e2e_flow(self):
        port = 8765
        base_url = f"http://127.0.0.1:{port}"
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, NEURALCLEAR_DB=str(Path(tmp) / "sandbox.db"))
            process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "server.app:app", "--port", str(port)],
                cwd=str(Path(__file__).resolve().parents[1]),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                client = NeuralClearHTTPClient(base_url, api_key="dev_neuralclear_key")
                for _ in range(50):
                    try:
                        manifest = client.get_manifest()
                        if manifest.get("agent_id") == "agent.pdf_summarizer":
                            break
                    except Exception:
                        time.sleep(0.1)
                else:
                    self.fail("server did not start")

                quote = client.request_quote(
                    "buyer.research", "agent.pdf_summarizer", "summarize.pdf"
                )
                task = client.submit_task(
                    {
                        "buyer": "buyer.research",
                        "provider": "agent.pdf_summarizer",
                        "quote_id": quote["quote_id"],
                        "payload": {"text": "Process E2E PDF summary."},
                    }
                )
                receipt = client.get_receipt(task["result"]["receipt"]["receipt_id"])
                balances = client.balances()

                self.assertEqual(receipt["amount"], 50)
                self.assertEqual(balances["balances"]["buyer.research"], 945)
                self.assertEqual(balances["balances"]["agent.pdf_summarizer"], 50)
                self.assertEqual(balances["fee_pool"], 5)
                self.assertEqual(balances["total_supply"], 1_000)
            finally:
                process.terminate()
                process.wait(timeout=5)
