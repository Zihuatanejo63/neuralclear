"""Offline guard tests only; no Stripe calls, credentials or test transactions."""

from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from examples.escrow_channel_live_test import (
    ObservedStripeHTTP,
    NoRedirect,
    read_test_key,
    redact,
    run,
)
from neuralclear.core import ProtocolError
from neuralclear.verify import verify


class StripeLiveRunnerTests(unittest.TestCase):
    def test_recorded_real_run_receipt_verifies_offline(self):
        path = Path(__file__).resolve().parents[1] / "docs/p0-live-stripe-evidence-2026-10-22.json"
        evidence = json.loads(path.read_text())
        self.assertTrue(verify(evidence["receipt"], evidence["chain"],
                               {"clearing": ("Ed25519", bytes.fromhex(evidence["public_key_hex"]))}))

    def test_key_file_and_live_key_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stripe.env"
            path.write_text('export STRIPE_SECRET_KEY="sk_test_offlinefixture" # comment\n')
            self.assertEqual(read_test_key(path), "sk_test_offlinefixture")
            path.write_text("STRIPE_SECRET_KEY=sk_live_offlinefixture\n")
            with self.assertRaises(ProtocolError):
                read_test_key(path)
        with self.assertRaises(ProtocolError):
            ObservedStripeHTTP("sk_live_offlinefixture", {"requests": []})

    def test_raw_error_message_is_redacted_without_dumping_response(self):
        secret = "sk_test_offlinefixture"
        evidence = {"requests": []}
        http = ObservedStripeHTTP(secret, evidence)
        body = {
            "error": {
                "type": "invalid_request_error",
                "message": "Invalid key: " + secret,
                "client_secret": "not-for-output",
            }
        }
        error = HTTPError(
            "https://api.stripe.com/v1/account",
            401,
            "Unauthorized",
            {"Request-Id": "req_fixture"},
            BytesIO(json.dumps(body).encode()),
        )
        with patch.object(http.transport, "open", side_effect=error):
            with self.assertRaises(ProtocolError):
                http.request("GET", "account")
        serialized = json.dumps(evidence)
        self.assertNotIn(secret, serialized)
        self.assertNotIn("not-for-output", serialized)
        self.assertEqual(evidence["requests"][0]["http_status"], 401)
        self.assertIn("Invalid key:", evidence["requests"][0]["error"]["message"])

    def test_success_response_does_not_log_client_secret(self):
        evidence = {"requests": []}
        http = ObservedStripeHTTP("sk_test_offlinefixture", evidence)
        response = dict(
            id="pi_fixture",
            object="payment_intent",
            status="succeeded",
            livemode=False,
            client_secret="must-not-leak",
        )
        with patch.object(
            http.transport, "open", return_value=BytesIO(json.dumps(response).encode())
        ):
            self.assertEqual(http.request("GET", "payment_intents/pi_fixture")["id"], "pi_fixture")
        self.assertNotIn("must-not-leak", json.dumps(evidence))

    def test_live_object_and_redirect_rejected(self):
        http = ObservedStripeHTTP("sk_test_offlinefixture", {"requests": []})
        with patch.object(http.transport, "open", return_value=BytesIO(b'{"livemode":true}')):
            with self.assertRaises(ProtocolError):
                http.request("GET", "balance")
        with self.assertRaises(ProtocolError):
            NoRedirect().redirect_request(
                Request("https://api.stripe.com/v1/account"),
                None,
                302,
                "redirect",
                {},
                "https://example.com",
            )

    def test_existing_run_directory_is_not_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileExistsError):
                run(None, {}, Path(tmp))

    def test_error_redaction_covers_client_secret(self):
        result = redact("pi_ABC_secret_DEF sk_test_otherfixture", "sk_test_offlinefixture")
        self.assertNotIn("DEF", result)
        self.assertNotIn("otherfixture", result)
