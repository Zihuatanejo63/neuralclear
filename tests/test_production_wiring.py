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
                "NEURALCLEAR_KMS_ENV": "live",
                "NEURALCLEAR_REPLAY_STORE": self.replay_path,
                "NEURALCLEAR_SIGNING_KEY_ID": "kid-receipt",
            },
        )
        self.env.start()
        self.kms = PersistentKms(self.kms_path, environment="live")
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
        self.assertTrue(proof.verify_with(HMACKey("test-hmac")))
        with self.assertRaisesRegex(ProtocolError, "replayed nonce"):
            proof.verify_with(HMACKey("test-hmac"))

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
            self.assertEqual(authed.status_code, 200)
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
