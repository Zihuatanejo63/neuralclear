"""Integration: production issue and verify use PersistentKms and ReplayStore.

Generated test keys only. No live signing, payment, or webhook material.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from neuralclear import ed25519
from neuralclear.core import ProtocolError
from neuralclear.escrow import EscrowLedger
from neuralclear.key_rotation import issue_key, retire_key
from neuralclear.kms import PersistentKms, set_process_kms
from neuralclear.mandates import issue_mandate
from neuralclear.production_guard import assert_escrow_app_ready, require_known_mode
from neuralclear.proofs import HMACKey, SignedResultProof
from neuralclear.replay import ReplayStore
from neuralclear.wire import sign, verify_signature
from tests.test_escrow import ledger_at

try:
    from fastapi.testclient import TestClient
    import server.app as app_module
    from server.signing import sign_receipt, verify_receipt
except ImportError:
    TestClient = None
    app_module = None
    sign_receipt = None
    verify_receipt = None


class WiringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.kms_path = str(Path(self.tmp.name) / "kms.db")
        self.replay_path = str(Path(self.tmp.name) / "replay.db")
        self.env = patch.dict(
            os.environ,
            {
                "NEURALCLEAR_MODE": "production",
                "NEURALCLEAR_KMS_ENV": "test",
                "NEURALCLEAR_REPLAY_STORE": self.replay_path,
                "NEURALCLEAR_SIGNING_KEY_ID": "kid-receipt",
            },
        )
        self.env.start()
        self.kms = PersistentKms(self.kms_path, environment="test")
        issue_key(
            self.kms,
            purpose="receipt",
            kid="kid-receipt",
            now=1,
            roles={"receipt", "mandate", "result", "decision"},
        )
        set_process_kms(self.kms)

    def tearDown(self):
        set_process_kms(None)
        self.env.stop()
        self.tmp.cleanup()

    def test_escrow_issue_uses_cryptography_not_the_reference_signer(self):
        def forbidden(*_args, **_kwargs):
            raise AssertionError("reference ed25519 signer was called")

        with patch.object(ed25519, "sign", forbidden), patch.object(ed25519, "verify", forbidden):
            mandate = issue_mandate(
                {
                    "mandate_id": "m1",
                    "owner": "owner",
                    "agent": "agent",
                    "currency": "usd",
                    "allowed_capabilities": ["work"],
                    "max_per_task": 10,
                    "max_daily": 10,
                    "max_total": 10,
                    "valid_until": 9_999_999_999,
                    "requires_human_approval_above": 10,
                },
                b"",
                "kid-receipt",
                signer=self.kms,
            )
            verify_signature(mandate, {}, domain="mandate", signer=self.kms)
            ledger = ledger_at("SETTLED")
            receipt = ledger.receipt("tx", key=b"", key_id="kid-receipt", signer=self.kms)
            verify_signature(receipt, {}, domain="receipt", signer=self.kms)
        self.assertEqual(mandate["algorithm"], "Ed25519")
        self.assertIsInstance(mandate["signed_at"], int)
        self.assertTrue(mandate["nonce"])
        import sqlite3

        seen = sqlite3.connect(self.replay_path).execute(
            "SELECT phase, message_id FROM seen_nonces"
        ).fetchall()
        phases = {row[0] for row in seen}
        self.assertIn("issue", phases)
        self.assertIn("verify", phases)

    def test_revoked_kid_fails_commercial_and_escrow_verify(self):
        if sign_receipt is None:
            self.skipTest("server signing unavailable")
        commercial = sign_receipt(
            {
                "receipt_id": "rcpt_wire",
                "transaction_id": "tx",
                "buyer": "buyer",
                "provider": "provider",
                "amount": 1,
                "fee": 0,
                "currency": "CC",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "result_hash": "ab",
            }
        )
        self.assertTrue(commercial["signature"].startswith("ed25519:"))
        verify_receipt(commercial)
        retire_key(self.kms, "kid-receipt")
        with self.assertRaisesRegex(ProtocolError, "revoked key"):
            verify_receipt(commercial)
        with self.assertRaisesRegex(ProtocolError, "revoked key"):
            verify_signature(
                {
                    "transaction_id": "tx",
                    "algorithm": "Ed25519",
                    "key_id": "kid-receipt",
                    "nonce": "n",
                    "signed_at": 10,
                    "signature": "00",
                },
                {},
                domain="receipt",
                signer=self.kms,
            )

    def test_hmac_result_proof_hits_replay_store(self):
        proof = SignedResultProof.sign(HMACKey("test-hmac"), "agent", "work", {"ok": True})
        self.assertTrue(proof.nonce)
        self.assertEqual(proof.to_json()["nonce"], proof.nonce)
        self.assertEqual(proof.to_json()["signed_at_unix"], proof.signed_at_unix)
        self.assertTrue(proof.verify_with(HMACKey("test-hmac")))
        with self.assertRaisesRegex(ProtocolError, "replayed nonce"):
            proof.verify_with(HMACKey("test-hmac"))

    def test_production_refuses_hmac_and_envelopes_without_nonce(self):
        with self.assertRaisesRegex(ProtocolError, "persistent KMS"):
            sign({"note": "sandbox-only"}, b"test-signing-secret", "kid", "HMAC-SHA256")
        with self.assertRaisesRegex(ProtocolError, "nonce and integer timestamp"):
            verify_signature(
                {"algorithm": "Ed25519", "key_id": "kid-receipt", "signature": "ab"},
                {},
                signer=self.kms,
            )
        with self.assertRaisesRegex(ProtocolError, "unknown key"):
            sign({"transaction_id": "tx"}, b"", "no-such-kid", signer=self.kms, domain="result")

    def test_unknown_mode_fails_closed(self):
        with patch.dict(os.environ, {"NEURALCLEAR_MODE": "staging"}):
            with self.assertRaisesRegex(ProtocolError, "unknown NEURALCLEAR_MODE"):
                require_known_mode()

    def test_raw_receipt_key_is_rejected_for_a_persistent_signer(self):
        with self.assertRaisesRegex(ProtocolError, "raw receipt_key"):
            assert_escrow_app_ready(
                write_key="operator-api-key-value",
                signer=self.kms,
                algorithm="Ed25519",
                receipt_key=b"\x01" * 32,
            )

    def test_replay_integrity_error_rolls_back(self):
        store = ReplayStore(str(Path(self.tmp.name) / "rollback.db"), skew_seconds=30, ttl_seconds=30)
        store.admit(message_id="m", nonce="once", timestamp=1_000, now=1_000)
        with self.assertRaisesRegex(ProtocolError, "replayed nonce"):
            store.admit(message_id="m", nonce="once", timestamp=1_000, now=1_000)
        store.admit(message_id="m2", nonce="twice", timestamp=1_000, now=1_000)


@unittest.skipIf(TestClient is None, "HTTP extras not installed")
class ProductionRouteTests(unittest.TestCase):
    def test_production_reads_require_auth_and_conflict_is_409(self):
        client = TestClient(app_module.app)
        with patch.dict(os.environ, {"NEURALCLEAR_MODE": "production"}):
            for method, path, kwargs in (
                ("post", "/neuralclear/settlements", {"json": {"transaction_id": "missing"}}),
                ("get", "/neuralclear/balances", {}),
                ("get", "/dashboard/receipts", {}),
                ("get", "/dashboard/transactions", {}),
                ("get", "/dashboard/balances", {}),
            ):
                response = getattr(client, method)(path, **kwargs)
                self.assertEqual(response.status_code, 401, path)
            authed = client.get(
                "/neuralclear/balances",
                headers={"X-NeuralClear-API-Key": "test-api-key"},
            )
            self.assertEqual(authed.status_code, 401)
        quote = client.post(
            "/neuralclear/quote",
            json={"provider": "agent.pdf_summarizer", "capability": "summarize.pdf"},
            headers={"X-NeuralClear-API-Key": "test-api-key"},
        )
        body = {
            "buyer": "buyer.research",
            "provider": "agent.pdf_summarizer",
            "quote_id": quote.json()["quote_id"],
            "payload": {"text": "first"},
        }
        headers = {"X-NeuralClear-API-Key": "test-api-key", "Idempotency-Key": "wire-409"}
        first = client.post("/neuralclear/tasks", json=body, headers=headers)
        body["payload"] = {"text": "second"}
        second = client.post("/neuralclear/tasks", json=body, headers=headers)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)


@unittest.skipIf(TestClient is None, "HTTP extras not installed")
class EscrowProductionHttpTests(unittest.TestCase):
    def test_http_receipt_and_mandate_use_the_app_signer(self):
        from neuralclear.escrow import EscrowLedger
        from neuralclear.mandates import issue_mandate
        from server.escrow_api import HEADERS, create_escrow_app
        from tests.test_escrow import ledger_at

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        kms_path = str(Path(tmp.name) / "kms.db")
        replay_path = str(Path(tmp.name) / "replay.db")
        env = {
            "NEURALCLEAR_MODE": "production",
            "NEURALCLEAR_KMS_ENV": "test",
            "NEURALCLEAR_REPLAY_STORE": replay_path,
            "NEURALCLEAR_SIGNING_KEY_ID": "kid-http",
        }
        with patch.dict(os.environ, env):
            kms = PersistentKms(kms_path, environment="test")
            issue_key(
                kms,
                purpose="receipt",
                kid="kid-http",
                now=1,
                roles={"receipt", "mandate"},
            )
            settled = ledger_at("SETTLED")
            app = create_escrow_app(
                settled,
                write_key="operator-api-key-value",
                receipt_key=b"",
                receipt_key_id="kid-http",
                algorithm="Ed25519",
                mode="production",
                signer=kms,
            )
            client = TestClient(app)
            headers = {**HEADERS, "X-NeuralClear-API-Key": "operator-api-key-value"}
            denied = client.get(
                "/neuralclear/receipts/tx",
                headers={**HEADERS, "X-NeuralClear-API-Key": "test-api-key"},
            )
            self.assertEqual(denied.status_code, 401)

            def forbidden(*_args, **_kwargs):
                raise AssertionError("reference ed25519 signer was called")

            with patch.object(ed25519, "sign", forbidden), patch.object(ed25519, "verify", forbidden):
                issued = client.get("/neuralclear/receipts/tx", headers=headers)
            self.assertEqual(issued.status_code, 200, issued.text)
            receipt = issued.json()["receipt"]
            self.assertEqual(receipt["algorithm"], "Ed25519")
            self.assertEqual(receipt["key_id"], "kid-http")
            self.assertEqual(len(receipt["signature"]), 128)
            self.assertIsInstance(receipt["signed_at"], int)

            quoted = EscrowLedger(
                "usd",
                mandate_keys={"kid-http": ("buyer", "Ed25519", b"x")},
                signer=kms,
            )
            quoted.open_account("buyer", 100)
            quoted.open_account("provider")
            quote_app = create_escrow_app(
                quoted,
                write_key="operator-api-key-value",
                receipt_key=b"",
                receipt_key_id="kid-http",
                algorithm="Ed25519",
                mode="production",
                signer=kms,
            )
            mandate = issue_mandate(
                {
                    "mandate_id": "m-http",
                    "owner": "buyer",
                    "agent": "agent",
                    "currency": "usd",
                    "allowed_capabilities": ["work"],
                    "max_per_task": 50,
                    "max_daily": 50,
                    "max_total": 50,
                    "valid_until": 9_999_999_999,
                    "requires_human_approval_above": 50,
                },
                b"",
                "kid-http",
                signer=kms,
            )
            accepted = TestClient(quote_app).post(
                "/neuralclear/quote",
                headers=headers,
                json={
                    "quote": {
                        "transaction_id": "q1",
                        "buyer": "buyer",
                        "provider": "provider",
                        "amount": 10,
                    },
                    "mandate": mandate,
                    "agent": "agent",
                    "capability": "work",
                },
            )
            self.assertEqual(accepted.status_code, 200, accepted.text)
            self.assertEqual(quoted._signer, kms)


class ProductionProcessTests(unittest.TestCase):
    def test_reference_server_starts_in_production_and_returns_409(self):
        import subprocess
        import sys

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        kms_path = str(Path(tmp.name) / "kms.db")
        replay_path = str(Path(tmp.name) / "replay.db")
        env = os.environ.copy()
        env.update(
            {
                "NEURALCLEAR_MODE": "production",
                "NEURALCLEAR_KMS_ENV": "test",
                "NEURALCLEAR_KMS_PATH": kms_path,
                "NEURALCLEAR_REPLAY_STORE": replay_path,
                "NEURALCLEAR_API_KEY": "operator-api-key-value",
                "NEURALCLEAR_READ_API_KEY": "operator-read-key-value",
                "NEURALCLEAR_WRITE_API_KEY": "operator-api-key-value",
                "NEURALCLEAR_SIGNING_KEY_ID": "kid-proc",
                "NEURALCLEAR_SIGNING_SECRET": "",
            }
        )
        with patch.dict(os.environ, {"NEURALCLEAR_KMS_ENV": "test"}):
            kms = PersistentKms(kms_path, environment="test")
            issue_key(kms, purpose="mandate", kid="kid-proc", now=1, roles={"mandate", "receipt"})
        script = r"""
import os
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from neuralclear import SettlementCredit, SpendingMandate
from neuralclear.kms import get_process_kms
from neuralclear.mandate_auth import sign_spending_mandate
import server.app as app

kms = get_process_kms()
assert kms is not None and kms.persistent and kms.environment == "test"
mandate = SpendingMandate(
    owner="buyer.research",
    agent="buyer.research.agent",
    allowed_capabilities=["summarize.pdf"],
    max_per_task=SettlementCredit(100, "CC"),
    max_daily=SettlementCredit(1000, "CC"),
    valid_until=(datetime.now(timezone.utc) + timedelta(days=1)).timestamp(),
    requires_human_approval_above=SettlementCredit(500, "CC"),
    signature="placeholder",
)
signature = sign_spending_mandate(
    mandate, kms, os.environ["NEURALCLEAR_SIGNING_KEY_ID"], now=int(mandate.valid_until) - 10
)
client = TestClient(app.app)
key = os.environ["NEURALCLEAR_API_KEY"]
disputes = client.get("/dashboard/disputes")
assert disputes.status_code == 401, disputes.status_code
dev = client.get("/dashboard/disputes", headers={"X-NeuralClear-API-Key": "test-api-key"})
assert dev.status_code == 401, dev.status_code
opened = client.get("/dashboard/disputes", headers={"X-NeuralClear-API-Key": key})
assert opened.status_code == 200, opened.text
quote = client.post(
    "/neuralclear/quote",
    json={"provider": "agent.pdf_summarizer", "capability": "summarize.pdf"},
    headers={"X-NeuralClear-API-Key": key},
)
assert quote.status_code == 200, quote.text
body = {
    "buyer": "buyer.research",
    "provider": "agent.pdf_summarizer",
    "quote_id": quote.json()["quote_id"],
    "payload": {"text": "first"},
    "mandate": {
        "owner": mandate.owner,
        "agent": mandate.agent,
        "allowed_capabilities": mandate.allowed_capabilities,
        "max_per_task": mandate.max_per_task.to_json(),
        "max_daily": mandate.max_daily.to_json(),
        "valid_until": mandate.valid_until,
        "requires_human_approval_above": mandate.requires_human_approval_above.to_json(),
        "signature": signature,
    },
}
headers = {"X-NeuralClear-API-Key": key, "Idempotency-Key": "prod-409"}
first = client.post("/neuralclear/tasks", json=body, headers=headers)
assert first.status_code == 200, first.text
body["payload"] = {"text": "second"}
second = client.post("/neuralclear/tasks", json=body, headers=headers)
assert second.status_code == 409, second.text
print("production-process-ok")
"""
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(Path(__file__).resolve().parents[1]),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("production-process-ok", completed.stdout)
