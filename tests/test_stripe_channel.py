"""HTTP is stubbed; the escrow port is a test implementation, not core Ledger."""

from io import BytesIO
import json
import unittest
from urllib.parse import parse_qs

from neuralclear.core import ProtocolError
from neuralclear.stripe_channel import Funding, NetSettlement, StripeChannel, StripeHTTP


class StubLedger:
    def __init__(self):
        self.fundings = {}
        self.credited = {}
        self.escrow = 0
        self.net = None
        self.records = {}
        self.reserved = False

    def bind_funding(self, funding, key):
        identity = (funding.buyer, key)
        if identity in self.fundings and self.fundings[identity] != funding:
            raise ProtocolError("idempotency key conflict")
        self.fundings[identity] = funding
        return funding

    def credit_escrow(self, intent_id, funding):
        if intent_id in self.credited:
            if self.credited[intent_id] != funding:
                raise ProtocolError("idempotency key conflict")
            return
        self.credited[intent_id] = funding
        self.escrow += funding.amount

    def reserve_settlement(self, settlement_id, key):
        if self.net is None or self.net.settlement_id != settlement_id:
            raise ProtocolError("no finalized net settlement")
        self.reserved = True
        return self.net

    def record_payout(self, settlement_id, transfer, payout):
        self.records[settlement_id] = (transfer, payout)


class FakeStripe:
    def __init__(self):
        self.calls = []
        self.intents = {}
        self.responses = {}
        self.fail_payout = False

    def __call__(self, request, timeout):
        fields = {
            key: values[0] for key, values in parse_qs((request.data or b"").decode()).items()
        }
        self.calls.append((request, fields))
        path = request.full_url.split("/v1/")[1]
        if request.method == "GET":
            result = self.intents[path.split("/")[1]]
        else:
            identity = (path, request.get_header("Idempotency-key"))
            if path == "payouts" and self.fail_payout:
                self.fail_payout = False
                raise TimeoutError()
            if identity not in self.responses:
                prefix = {"payment_intents": "pi", "transfers": "tr", "payouts": "po"}[path]
                result = {
                    "id": prefix + "_123",
                    "amount": int(fields["amount"]),
                    "currency": fields["currency"],
                    "status": "pending",
                    "metadata": {
                        key[9:-1]: value
                        for key, value in fields.items()
                        if key.startswith("metadata[")
                    },
                }
                self.responses[identity] = result
                if path == "transfers":
                    result["destination"] = fields["destination"]
                self.intents[result["id"]] = result
            result = self.responses[identity]
        return BytesIO(json.dumps(result).encode())


class StripeChannelTests(unittest.TestCase):
    def setUp(self):
        self.ledger = StubLedger()
        self.stripe = FakeStripe()
        self.channel = StripeChannel(self.ledger, StripeHTTP("sk_test_fake", opener=self.stripe))
        self.funding = Funding("buyer", "escrow1", 1000, "usd")

    def fund(self):
        intent = self.channel.create_deposit(self.funding, idempotency_key="deposit1")
        self.assertEqual(self.ledger.escrow, 0)
        self.stripe.intents[intent["id"]].update(status="succeeded", amount_received=1000)
        return self.channel.confirm_deposit(intent["id"], self.funding, idempotency_key="deposit1")

    def test_deposit_credits_escrow_only_after_success(self):
        self.fund()
        self.assertEqual(self.ledger.escrow, 1000)
        request, fields = self.stripe.calls[0]
        self.assertEqual(fields["amount"], "1000")
        self.assertEqual(fields["currency"], "usd")
        self.assertTrue(request.get_header("Idempotency-key"))
        self.assertEqual(request.get_header("Authorization"), "Bearer sk_test_fake")

    def test_duplicate_callback_is_idempotent_across_adapter_restart(self):
        self.fund()
        restarted = StripeChannel(self.ledger, StripeHTTP("sk_test_fake", opener=self.stripe))
        restarted.confirm_deposit("pi_123", self.funding, idempotency_key="deposit1")
        self.assertEqual(self.ledger.escrow, 1000)
        self.assertEqual(len(self.ledger.credited), 1)

    def test_conflicting_payload_rejected_before_http(self):
        self.channel.create_deposit(self.funding, idempotency_key="deposit1")
        with self.assertRaisesRegex(ProtocolError, "idempotency key conflict"):
            self.channel.create_deposit(
                Funding("buyer", "other", 2000, "usd"), idempotency_key="deposit1"
            )
        self.assertEqual(len(self.stripe.calls), 1)

    def test_unsuccessful_or_mismatched_deposit_not_credited(self):
        self.channel.create_deposit(self.funding, idempotency_key="deposit1")
        for changes in (
            {"status": "processing"},
            {"status": "succeeded", "amount_received": 999},
            {"amount_received": 1000, "currency": "eur"},
            {"currency": "usd", "metadata": {}},
        ):
            self.stripe.intents["pi_123"].update(changes)
            with self.assertRaises(ProtocolError):
                self.channel.confirm_deposit("pi_123", self.funding, idempotency_key="deposit1")
            self.assertEqual(self.ledger.escrow, 0)

    def test_net_settlement_payout(self):
        self.fund()
        # Engine fixture supplies final net proceeds after metering and fee deduction.
        self.ledger.net = NetSettlement("net1", "provider", "acct_provider", 900, "usd")
        payout = self.channel.payout("net1", idempotency_key="withdraw1")
        self.assertEqual(payout["amount"], 900)
        transfer_request, transfer = self.stripe.calls[-2]
        payout_request, fields = self.stripe.calls[-1]
        self.assertEqual(transfer["destination"], "acct_provider")
        self.assertEqual(payout_request.get_header("Stripe-account"), "acct_provider")
        self.assertNotEqual(
            transfer_request.get_header("Idempotency-key"),
            payout_request.get_header("Idempotency-key"),
        )
        self.assertTrue(self.ledger.reserved)
        self.assertEqual(self.ledger.records["net1"][1]["status"], "pending")
        self.stripe.intents["po_123"]["status"] = "paid"
        self.channel.reconcile_payout(self.ledger.net, self.ledger.records["net1"][0], "po_123")
        self.assertEqual(self.ledger.records["net1"][1]["status"], "paid")

    def test_payout_retry_does_not_repeat_transfer(self):
        self.ledger.net = NetSettlement("net1", "provider", "acct_provider", 900, "usd")
        self.stripe.fail_payout = True
        with self.assertRaisesRegex(ProtocolError, "outcome unknown"):
            self.channel.payout("net1", idempotency_key="first")
        self.channel.payout("net1", idempotency_key="retry")
        self.assertEqual(len(self.stripe.responses), 2)

    def test_unsettled_payout_rejected(self):
        with self.assertRaisesRegex(ProtocolError, "no finalized"):
            self.channel.payout("missing", idempotency_key="key")
        self.assertEqual(self.stripe.calls, [])

    def test_failed_payout_remains_reserved(self):
        self.ledger.net = NetSettlement("net1", "provider", "acct_provider", 900, "usd")
        self.channel.payout("net1", idempotency_key="key")
        self.stripe.intents["po_123"]["status"] = "failed"
        result = self.channel.reconcile_payout(
            self.ledger.net, self.ledger.records["net1"][0], "po_123"
        )
        self.assertEqual(result["status"], "failed")
        self.assertTrue(self.ledger.reserved)

    def test_http_error_does_not_expose_secret(self):
        from urllib.error import HTTPError

        def fail(request, timeout):
            raise HTTPError(request.full_url, 401, "sk_test_private", {}, None)

        http = StripeHTTP("sk_test_private", opener=fail)
        with self.assertRaisesRegex(ProtocolError, "Stripe HTTP error 401") as caught:
            http.request("GET", "payment_intents/pi_123")
        self.assertNotIn("sk_test_private", str(caught.exception))

    def test_invalid_money_and_identifiers(self):
        for amount, currency in [
            (True, "usd"),
            (1.5, "usd"),
            (0, "usd"),
            (-1, "usd"),
            (100, "CC"),
            (100, "USD"),
        ]:
            with self.subTest(amount=amount, currency=currency), self.assertRaises(ProtocolError):
                self.channel.create_deposit(
                    Funding("buyer", "escrow", amount, currency), idempotency_key="key"
                )
        with self.assertRaises(ProtocolError):
            self.channel.payment_status("pi_123/../../balance")
        self.assertEqual(self.stripe.calls, [])
