"""The credit sandbox and the fiat escrow ledger do not convert into each other."""

import unittest

from neuralclear.clearing import ClearingService, EscrowLedger as CreditLedger, FeePolicy
from neuralclear.core import ProtocolError, SettlementCredit
from neuralclear.escrow_channel import ClearingLedger
from neuralclear.gateway import ClearingGateway
from neuralclear.ledger_boundary import convert_credit_to_fiat, convert_fiat_to_credit
from neuralclear.provider import ProviderAgent
from neuralclear.stripe_channel import Funding, StripeChannel, StripeHTTP

try:
    from server.escrow_api import create_escrow_app
except ImportError:  # fastapi is optional
    create_escrow_app = None


class LedgerBoundaryTests(unittest.TestCase):
    def test_conversion_helpers_always_refuse(self):
        with self.assertRaisesRegex(ProtocolError, "credit-to-fiat"):
            convert_credit_to_fiat(100, "CC", "usd")
        with self.assertRaisesRegex(ProtocolError, "fiat-to-credit"):
            convert_fiat_to_credit(100, "usd", "CC")
        with self.assertRaisesRegex(ProtocolError, "credit-to-fiat"):
            convert_credit_to_fiat(100, "CC", "CC")

    def test_stripe_ledger_rejects_credit_currency(self):
        for currency in ("CC", "cc", "USD", "us", "usd1"):
            with self.subTest(currency=currency):
                with self.assertRaises(ProtocolError):
                    ClearingLedger(currency=currency, provider_accounts={})
        ledger = ClearingLedger(currency="usd", provider_accounts={"provider": "acct_example"})
        self.assertEqual(ledger.currency, "usd")

    def test_sandbox_credits_reject_fiat_labels(self):
        with self.assertRaisesRegex(ProtocolError, "CC only"):
            SettlementCredit(1, "usd")
        with self.assertRaisesRegex(ProtocolError, "CC only"):
            FeePolicy(currency="jpy")
        with self.assertRaisesRegex(ProtocolError, "CC only"):
            ProviderAgent("agent.example", currency="eur")
        self.assertEqual(SettlementCredit(1).currency, "CC")

    def test_stripe_channel_rejects_credit_ledger_and_has_no_refund(self):
        http = StripeHTTP("sk_test_offlinefixture")
        with self.assertRaisesRegex(ProtocolError, "credit ledger"):
            StripeChannel(CreditLedger(), http)
        with self.assertRaisesRegex(ProtocolError, "credit ledger"):
            StripeChannel(ClearingService(), http)
        self.assertFalse(any(name.startswith("refund") for name in StripeChannel.__dict__))
        with self.assertRaises(ProtocolError):
            StripeChannel(object(), http).create_deposit(
                Funding("buyer", "escrow", 100, "CC"), idempotency_key="key"
            )

    def test_gateway_rejects_fiat_ledger(self):
        fiat = ClearingLedger(currency="jpy", provider_accounts={})
        with self.assertRaisesRegex(ProtocolError, "CC sandbox"):
            ClearingGateway(clearing=fiat)

    def test_fiat_posting_does_not_change_credit_balances(self):
        credit = CreditLedger()
        credit.open_account("buyer", SettlementCredit(25))
        fiat = ClearingLedger(currency="usd", provider_accounts={"provider": "acct_example"})
        fiat.open_account("buyer", 0)
        before = credit.balance_of("buyer")
        with self.assertRaises(ProtocolError):
            convert_fiat_to_credit(40, fiat.currency, "CC")
        self.assertEqual(credit.balance_of("buyer"), before)
        self.assertEqual(credit.snapshot()["balances"]["buyer"], before)
        self.assertEqual(fiat.snapshot()["balances"]["buyer"], 0)

    @unittest.skipIf(create_escrow_app is None, "HTTP extras not installed")
    def test_escrow_http_app_rejects_credit_ledger(self):
        with self.assertRaisesRegex(ProtocolError, "credit ledger"):
            create_escrow_app(
                CreditLedger(),
                write_key="write",
                receipt_key=b"secret",
                receipt_key_id="key",
            )
        with self.assertRaisesRegex(ProtocolError, "credit ledger"):
            create_escrow_app(
                ClearingService(),
                write_key="write",
                receipt_key=b"secret",
                receipt_key_id="key",
            )
