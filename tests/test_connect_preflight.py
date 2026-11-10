import io
import json
import unittest

from neuralclear.core import ProtocolError
from neuralclear.stripe_channel import StripeChannel, StripeHTTP


class ConnectPreflightTests(unittest.TestCase):
    def channel(self, enabled):
        self.calls = []

        def opener(request, timeout):
            self.calls.append((request.method, request.full_url))
            if request.full_url.endswith("accounts?limit=1"):
                body = {"data": [{"id": "acct_provider"}] if enabled else []}
            else:
                body = {"id": "acct_created" if request.method == "POST" else "acct_platform"}
            return io.BytesIO(json.dumps(body).encode())

        return StripeChannel(None, StripeHTTP("offline-test", opener=opener))

    def test_unconfirmed_connect_blocks_before_creation(self):
        channel = self.channel(False)
        with self.assertRaisesRegex(ProtocolError, "dashboard.stripe.com/connect"):
            channel.create_connected_account({"country": "JP"}, idempotency_key="key")
        self.assertTrue(all(method == "GET" for method, _ in self.calls))

    def test_existing_connect_allows_creation(self):
        channel = self.channel(True)
        result = channel.create_connected_account({"country": "JP"}, idempotency_key="key")
        self.assertEqual(result["id"], "acct_created")
        self.assertEqual(self.calls[-1][0], "POST")

    def test_empty_enabled_platform_requires_operator_confirmation(self):
        channel = self.channel(False)
        self.assertEqual(
            channel.connect_preflight(operator_confirmed=True)["evidence"], "operator confirmation"
        )
