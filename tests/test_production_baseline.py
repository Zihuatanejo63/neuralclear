"""Production baseline controls. No live keys, no network, no webhook endpoint."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from neuralclear import ed25519
from neuralclear.core import ProtocolError, SpendingMandate, SettlementCredit
from neuralclear.escrow import EscrowLedger
from neuralclear.key_rotation import begin_overlap, issue_key, retire_key
from neuralclear.kms import LocalKms, redact_sensitive, set_process_kms
from neuralclear.mandate_auth import sign_spending_mandate
from neuralclear.production_guard import (
    assert_escrow_app_ready,
    assert_production_signer,
    assert_reference_server_ready,
)
from neuralclear.replay import ReplayStore, accept_signed_message
from neuralclear.secretcmp import const_equal
from server.ledger_store import ReferenceClearingService
from server.signing import verify_receipt
from tests.test_v03_sandbox import pdf_mandate

try:
    from server.escrow_api import create_escrow_app
except ImportError:
    create_escrow_app = None


class ProductionFailClosedTests(unittest.TestCase):
    def test_reference_signer_and_mock_proof_and_default_keys_are_refused(self):
        live = LocalKms(environment="live")
        with self.assertRaisesRegex(ProtocolError, "reference Ed25519"):
            assert_production_signer(ed25519)
        with self.assertRaisesRegex(ProtocolError, "development default"):
            assert_reference_server_ready(
                api_keys=["dev_neuralclear_key"],
                signer=live,
                proof_name="SIGNED_RESULT",
            )
        with self.assertRaisesRegex(ProtocolError, "missing"):
            assert_reference_server_ready(api_keys=[""], signer=live, proof_name="SIGNED_RESULT")
        with self.assertRaisesRegex(ProtocolError, "MockProof"):
            assert_reference_server_ready(
                api_keys=["operator-api-key-value"],
                signer=live,
                proof_name="MockProof",
            )
        with self.assertRaisesRegex(ProtocolError, "HMAC"):
            assert_escrow_app_ready(
                write_key="operator-api-key-value",
                signer=live,
                algorithm="HMAC-SHA256",
            )
        with self.assertRaisesRegex(ProtocolError, "explicit KMS"):
            assert_production_signer(None)

    def test_test_keys_cannot_enter_a_live_kms(self):
        live = LocalKms(environment="live")
        with self.assertRaisesRegex(ProtocolError, "another environment"):
            live.generate(
                purpose="receipt",
                kid="kid-test",
                not_before=1,
                roles={"receipt"},
                environment="test",
            )
        sandbox = LocalKms(environment="test")
        with self.assertRaisesRegex(ProtocolError, "persistent KMS"):
            assert_production_signer(sandbox)

    def test_images_and_env_example_do_not_bake_keys(self):
        root = Path(__file__).resolve().parents[1]
        dockerfile = (root / "Dockerfile").read_text()
        compose = (root / "docker-compose.yml").read_text()
        example = (root / ".env.example").read_text()
        self.assertNotIn("dev_neuralclear", dockerfile)
        self.assertNotIn("dev_neuralclear", compose)
        self.assertNotIn("=", example)
        self.assertIn("NEURALCLEAR_API_KEY", example)
        self.assertIn("NEURALCLEAR_SIGNING_SECRET", example)


class KeyRotationTests(unittest.TestCase):
    def test_overlap_then_revocation_for_commercial_and_escrow_purposes(self):
        for purpose, role in (("receipt", "receipt"), ("mandate", "mandate")):
            with self.subTest(purpose=purpose):
                kms = LocalKms(environment="test")
                issue_key(kms, purpose=purpose, kid="old", now=1_000, roles={role})
                issue_key(kms, purpose=purpose, kid="new", now=1_000, roles={role})
                begin_overlap(kms, "old", now=1_000, overlap_seconds=100)
                message = f"neuralclear-{purpose}".encode()
                old_sig = kms.sign("old", message, role=role, now=1_050)
                new_sig = kms.sign("new", message, role=role, now=1_050)
                kms.verify("old", message, old_sig, now=1_050)
                kms.verify("new", message, new_sig, now=1_050)
                retire_key(kms, "old")
                with self.assertRaisesRegex(ProtocolError, "revoked key"):
                    kms.verify("old", message, old_sig, now=1_050)
                kms.verify("new", message, new_sig, now=1_050)
                with self.assertRaisesRegex(ProtocolError, "unknown key"):
                    kms.verify("missing", message, new_sig, now=1_050)


class ReplayAndIdempotencyTests(unittest.TestCase):
    def test_nonce_replay_expiry_skew_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "replay.db")
            store = ReplayStore(path, skew_seconds=120, ttl_seconds=60)
            body = {"nonce": "n-1", "timestamp": 1_000}
            accept_signed_message(body, store, message_id="commercial-receipt", now=1_000)
            with self.assertRaisesRegex(ProtocolError, "replayed nonce"):
                accept_signed_message(body, store, message_id="commercial-receipt", now=1_000)
            store.close()
            restarted = ReplayStore(path, skew_seconds=120, ttl_seconds=60)
            with self.assertRaisesRegex(ProtocolError, "replayed nonce"):
                accept_signed_message(body, restarted, message_id="hmac-result-proof", now=1_010)
            for kind in ("mandate", "result", "receipt", "decision"):
                fresh = {"nonce": "n-" + kind, "timestamp": 1_000}
                accept_signed_message(fresh, restarted, message_id=kind, now=1_000)
            with self.assertRaisesRegex(ProtocolError, "clock skew"):
                accept_signed_message(
                    {"nonce": "future", "timestamp": 1_200},
                    restarted,
                    message_id="future",
                    now=1_000,
                )
            with self.assertRaisesRegex(ProtocolError, "signed message expired"):
                accept_signed_message(
                    {"nonce": "old", "timestamp": 900},
                    restarted,
                    message_id="old",
                    now=1_000,
                )
            restarted.close()

    def test_submit_without_idempotency_key_is_rejected_and_conflict_stays_409(self):
        service = ReferenceClearingService()
        quote = service.request_quote("agent.pdf_summarizer", "summarize.pdf")
        with self.assertRaisesRegex(ProtocolError, "idempotency key required"):
            service.submit_task(
                task_id="task_missing_key",
                quote_id=str(quote["quote_id"]),
                buyer="buyer.research",
                provider="agent.pdf_summarizer",
                payload={"text": "no key"},
                mandate=pdf_mandate(),
            )
        service.idempotency_ttl = 5
        service.submit_task(
            task_id="task_ttl",
            quote_id=str(quote["quote_id"]),
            buyer="buyer.research",
            provider="agent.pdf_summarizer",
            payload={"text": "ttl"},
            mandate=pdf_mandate(),
            idempotency_key="idem-ttl",
        )
        service.idempotency_records[("buyer.research", "idem-ttl")]["expires_at"] = 0
        again = service.submit_task(
            task_id="task_ttl_2",
            quote_id=str(quote["quote_id"]),
            buyer="buyer.research",
            provider="agent.pdf_summarizer",
            payload={"text": "ttl"},
            mandate=pdf_mandate(),
            idempotency_key="idem-ttl",
        )
        self.assertNotEqual(again["task_id"], "task_ttl")

    def test_commercial_receipt_has_key_id(self):
        service = ReferenceClearingService()
        quote = service.request_quote("agent.pdf_summarizer", "summarize.pdf")
        task = service.submit_task(
            task_id="task_kid",
            quote_id=str(quote["quote_id"]),
            buyer="buyer.research",
            provider="agent.pdf_summarizer",
            payload={"text": "kid"},
            mandate=pdf_mandate(),
            idempotency_key="idem-kid",
        )
        receipt = task["result"]["receipt"]
        self.assertEqual(receipt["key_id"], "test-receipt")
        self.assertTrue(receipt["nonce"])
        self.assertTrue(verify_receipt(receipt))


class MandateAndRedactionTests(unittest.TestCase):
    def test_unverified_mandate_does_not_issue_a_production_receipt(self):
        kms = LocalKms(environment="live")
        issue_key(kms, purpose="mandate", kid="owner", now=1, roles={"mandate"})
        service = ReferenceClearingService()
        quote = service.request_quote("agent.pdf_summarizer", "summarize.pdf")
        with patch.dict(os.environ, {"NEURALCLEAR_MODE": "production"}):
            set_process_kms(kms)
            try:
                with self.assertRaisesRegex(ProtocolError, "mandate signature"):
                    service.submit_task(
                        task_id="task_bad_mandate",
                        quote_id=str(quote["quote_id"]),
                        buyer="buyer.research",
                        provider="agent.pdf_summarizer",
                        payload={"text": "no"},
                        mandate=pdf_mandate(),
                        idempotency_key="idem-bad",
                    )
                self.assertEqual(service.receipts, {})
                signed = pdf_mandate()
                signed = SpendingMandate(
                    owner=signed.owner,
                    agent=signed.agent,
                    allowed_capabilities=signed.allowed_capabilities,
                    max_per_task=signed.max_per_task,
                    max_daily=signed.max_daily,
                    valid_until=signed.valid_until,
                    requires_human_approval_above=signed.requires_human_approval_above,
                    signature=sign_spending_mandate(signed, kms, "owner", now=10),
                )
                with self.assertRaisesRegex(ProtocolError, "MockProof is not allowed in production"):
                    service.submit_task(
                        task_id="task_mock",
                        quote_id=str(quote["quote_id"]),
                        buyer="buyer.research",
                        provider="agent.pdf_summarizer",
                        payload={"text": "still mock"},
                        mandate=signed,
                        idempotency_key="idem-mock",
                    )
                self.assertEqual(service.receipts, {})
            finally:
                set_process_kms(None)

    def test_errors_redact_private_key_material(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private = Ed25519PrivateKey.generate()
        secret = private.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        leaked = f"sign failed {secret.hex()} sk_test_notalive"
        cleaned = redact_sensitive(leaked, [secret, "sk_test_notalive"])
        self.assertNotIn(secret.hex(), cleaned)
        self.assertNotIn("notalive", cleaned)
        kms = LocalKms(environment="test")
        issue_key(kms, purpose="receipt", kid="kid", now=1, roles={"receipt"})

        class Boom:
            def sign(self, _message):
                raise RuntimeError("leak " + secret.hex())

        kms._private["kid"] = Boom()
        with self.assertRaisesRegex(ProtocolError, "signature operation failed") as caught:
            kms.sign("kid", b"m", role="receipt", now=1)
        self.assertNotIn(secret.hex(), str(caught.exception))

    def test_const_equal_rejects_different_lengths(self):
        self.assertTrue(const_equal("test-api-key", "test-api-key"))
        self.assertFalse(const_equal("short", "test-api-key"))
        self.assertFalse(const_equal(None, "test-api-key"))
        self.assertFalse(const_equal("test-api-key", ""))

    @unittest.skipIf(create_escrow_app is None, "HTTP extras not installed")
    def test_production_escrow_app_refuses_reference_signer(self):
        ledger = EscrowLedger(currency="usd")
        with self.assertRaisesRegex(ProtocolError, "reference Ed25519|explicit KMS|HMAC"):
            create_escrow_app(
                ledger,
                write_key="operator-api-key-value",
                receipt_key=b"not-a-live-key",
                receipt_key_id="kid",
                algorithm="Ed25519",
                mode="production",
                signer=ed25519,
            )
