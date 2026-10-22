import unittest

try:
    from fastapi.testclient import TestClient
    from server.escrow_api import create_escrow_app, HEADERS, error_code
except ImportError:
    TestClient = None

from neuralclear.escrow import EscrowLedger


@unittest.skipIf(TestClient is None, "HTTP extras not installed")
class EscrowHTTPTests(unittest.TestCase):
    def setUp(self):
        self.ledger = EscrowLedger()
        self.ledger.open_account("buyer", 100)
        self.ledger.open_account("provider")
        self.ledger.create("tx", "buyer", "provider", 50, 5)
        self.client = TestClient(
            create_escrow_app(
                self.ledger,
                write_key="write",
                receipt_key=b"secret",
                receipt_key_id="key",
                algorithm="HMAC-SHA256",
            )
        )

    def test_profile_version_negotiation(self):
        discovery = self.client.get("/.well-known/neuralclear/agent.json")
        self.assertEqual(discovery.status_code, 200)
        for headers in ({}, dict(HEADERS, **{"X-NeuralClear-Version": "2"})):
            response = self.client.get("/neuralclear/tasks/tx", headers=headers)
            self.assertEqual(response.status_code, 406)
            self.assertEqual(response.json()["error"]["code"], "UNSUPPORTED_VERSION")
        response = self.client.get("/neuralclear/tasks/tx", headers=HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-NeuralClear-Version"], "1")

    def test_stable_errors_and_write_auth(self):
        headers = dict(HEADERS, **{"X-NeuralClear-API-Key": "write"})
        response = self.client.post(
            "/neuralclear/tasks", headers=HEADERS, json={"transaction_id": "tx"}
        )
        self.assertEqual(response.status_code, 401)
        response = self.client.post(
            "/neuralclear/tasks", headers=headers, json={"transaction_id": "tx"}
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "INVALID_STATE_TRANSITION")
        self.assertEqual(error_code("insufficient credit"), "INSUFFICIENT_CREDIT")
        self.assertEqual(error_code("mandate expired"), "MANDATE_EXPIRED")
        self.ledger.transition("tx", "QUOTE_ACCEPTED")
        self.assertEqual(
            self.client.post(
                "/neuralclear/tasks", headers=headers, json={"transaction_id": "tx"}
            ).status_code,
            200,
        )

    def test_duplicate_json_and_unknown_fields_rejected(self):
        headers = dict(
            HEADERS, **{"X-NeuralClear-API-Key": "write", "Content-Type": "application/json"}
        )
        for content in (
            '{"transaction_id":"tx","transaction_id":"other"}',
            '{"transaction_id":"tx","extra":1}',
            '{"transaction_id":NaN}',
        ):
            response = self.client.post("/neuralclear/tasks", headers=headers, content=content)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["error"]["code"], "INVALID_REQUEST")

    def test_spec_error_code_mapping(self):
        cases = {
            "quote expired": "QUOTE_EXPIRED",
            "insufficient credit": "INSUFFICIENT_CREDIT",
            "capability not allowed": "CAPABILITY_NOT_ALLOWED",
            "mandate expired": "MANDATE_EXPIRED",
            "mandate daily limit": "MANDATE_LIMIT_EXCEEDED",
            "mandate currency mismatch": "MANDATE_CURRENCY_MISMATCH",
            "signature mismatch": "PROOF_VERIFICATION_FAILED",
            "invalid transition": "INVALID_STATE_TRANSITION",
            "ledger invariant failed": "LEDGER_INVARIANT_FAILED",
            "invalid parties": "UNKNOWN_AGENT",
        }
        for message, code in cases.items():
            self.assertEqual(error_code(message), code)
