"""Stripe on/off ramp; all amounts are integer currency minor units.

The current core Ledger has no escrow or withdrawal API. Applications must supply
ChannelLedger with atomic, durable implementations before using this with money.
No automatic conversion from CC to fiat is implied: the ledger owns that mapping.
Task metering, netting, fees and receipt signing remain entirely in the ledger.
Stripe is a payment processor, not a legal escrow service.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .core import ProtocolError


@dataclass(frozen=True)
class Funding:
    buyer: str
    escrow_id: str
    amount: int
    currency: str


@dataclass(frozen=True)
class NetSettlement:
    settlement_id: str
    provider: str
    connected_account: str
    amount: int
    currency: str


class ChannelLedger(Protocol):
    """Ledger-owned durable boundary, including the retry/outbox records.

    bind_funding atomically binds (buyer, key) to Funding and rejects changed
    payloads with ProtocolError('idempotency key conflict'). credit_escrow must
    atomically deduplicate by PaymentIntent ID AND credit the bound escrow.
    reserve_settlement returns an immutable, finalized net amount and approved
    provider account; it atomically reserves the funds against further spending.
    Repeated calls (even with different keys) return the same reservation; changed
    key payloads conflict. record_payout atomically records Stripe IDs/status and
    retires the reservation only once on paid. Failed/canceled payouts remain
    reserved for explicit reconciliation; never automatically refund or retry
    with a fresh key. All methods must be safe across processes and restarts.
    """

    def bind_funding(self, funding: Funding, key: str) -> Funding: ...

    def credit_escrow(self, payment_intent_id: str, funding: Funding) -> None: ...

    def reserve_settlement(self, settlement_id: str, key: str) -> NetSettlement: ...

    def record_payout(self, settlement_id: str, transfer: dict, payout: dict) -> None: ...


class StripeHTTP:
    """Inject an opener for tests. No automatic retries or secret-bearing errors."""

    def __init__(self, secret_key: str, *, opener=urlopen, timeout: float = 15) -> None:
        if not secret_key or "\n" in secret_key or "\r" in secret_key:
            raise ProtocolError("Stripe secret key required")
        self.secret_key = secret_key
        self.opener = opener
        self.timeout = timeout

    def request(self, method: str, path: str, *, data=None, key=None, account=None) -> dict:
        headers = {"Authorization": f"Bearer {self.secret_key}"}
        if key:
            headers["Idempotency-Key"] = key
        if account:
            headers["Stripe-Account"] = account
        body = None
        if data is not None:
            body = urlencode(data).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = Request("https://api.stripe.com/v1/" + path, body, headers, method=method)
        try:
            with self.opener(request, timeout=self.timeout) as response:
                result = json.load(response)
        except HTTPError as exc:
            raise ProtocolError(f"Stripe HTTP error {exc.code}; retry with the same key") from None
        except (URLError, TimeoutError, OSError):
            raise ProtocolError(
                "Stripe transport error; outcome unknown, retain the same key"
            ) from None
        except (ValueError, UnicodeError):
            raise ProtocolError("invalid Stripe response") from None
        if not isinstance(result, dict) or "error" in result:
            raise ProtocolError("invalid Stripe response")
        return result


def _id(value: str, prefix: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(prefix + r"_[A-Za-z0-9]+", value):
        raise ProtocolError(f"invalid {prefix} identifier")
    return value


def _money(amount: int, currency: str) -> None:
    if type(amount) is not int or amount <= 0:
        raise ProtocolError("amount must be a positive integer in minor units")
    if not isinstance(currency, str) or not re.fullmatch(r"[a-z]{3}", currency):
        raise ProtocolError("currency must be an explicit lowercase ISO code")


def _key(*parts: str) -> str:
    if any(not isinstance(part, str) or not part.strip() for part in parts):
        raise ProtocolError("non-empty identity and idempotency key required")
    return "nc_" + hashlib.sha256(json.dumps(parts).encode()).hexdigest()


class StripeChannel:
    def __init__(self, ledger: ChannelLedger, http: StripeHTTP) -> None:
        self.ledger = ledger
        self.http = http

    def connect_preflight(self, *, operator_confirmed=False):
        """Read-only conservative probe; an empty list cannot prove activation.

        Stripe Account v1 has no documented platform connect_enabled flag.
        A newly enabled empty platform needs explicit operator confirmation.
        Never infer Connect activation from charges_enabled/payouts_enabled.
        """
        guide = "Confirm/enable Stripe Connect at https://dashboard.stripe.com/connect"
        try:
            platform = self.http.request("GET", "account")
            accounts = self.http.request("GET", "accounts?limit=1")
        except ProtocolError:
            raise ProtocolError("Connect readiness unavailable. " + guide) from None
        if not isinstance(accounts.get("data"), list):
            raise ProtocolError("Connect probe malformed. " + guide)
        if not accounts["data"] and operator_confirmed is not True:
            raise ProtocolError("Connect activation unconfirmed (empty registry). " + guide)
        return {
            "platform": _id(platform.get("id"), "acct"),
            "evidence": "existing account" if accounts["data"] else "operator confirmation",
        }

    def create_connected_account(self, data, *, idempotency_key, operator_confirmed=False):
        self.connect_preflight(operator_confirmed=operator_confirmed)
        try:
            return self.http.request(
                "POST", "accounts", data=data, key=_key("connect", idempotency_key)
            )
        except ProtocolError:
            raise ProtocolError(
                "Connect creation failed; reconcile the same idempotency key and check "
                "https://dashboard.stripe.com/connect"
            ) from None

    def create_deposit(self, funding: Funding, *, idempotency_key: str) -> dict:
        _money(funding.amount, funding.currency)
        key = _key("deposit", funding.buyer, funding.escrow_id, idempotency_key)
        bound = self.ledger.bind_funding(funding, idempotency_key)
        if bound != funding:
            raise ProtocolError("idempotency key conflict")
        return self.http.request(
            "POST",
            "payment_intents",
            key=key,
            data={
                "amount": funding.amount,
                "currency": funding.currency,
                "automatic_payment_methods[enabled]": "true",
                "metadata[buyer]": funding.buyer,
                "metadata[escrow_id]": funding.escrow_id,
                "metadata[funding_key]": idempotency_key,
            },
        )

    def confirm_deposit(
        self, payment_intent_id: str, funding: Funding, *, idempotency_key: str
    ) -> dict:
        """Re-fetch authenticated Stripe state; callback contents are never trusted.

        Payment collection/SCA happens in the client's Stripe flow. This method
        confirms the received funds, not the customer's card authorization.
        """
        _money(funding.amount, funding.currency)
        _key(funding.buyer, funding.escrow_id, idempotency_key)
        intent = self.payment_status(payment_intent_id)
        expected_metadata = {
            "buyer": funding.buyer,
            "escrow_id": funding.escrow_id,
            "funding_key": idempotency_key,
        }
        if (
            intent.get("id") != payment_intent_id
            or intent.get("status") != "succeeded"
            or type(intent.get("amount_received")) is not int
            or intent.get("amount_received") != funding.amount
            or intent.get("amount") != funding.amount
            or intent.get("currency") != funding.currency
            or intent.get("metadata") != expected_metadata
        ):
            raise ProtocolError("deposit not succeeded or funding mismatch")
        if self.ledger.bind_funding(funding, idempotency_key) != funding:
            raise ProtocolError("idempotency key conflict")
        self.ledger.credit_escrow(payment_intent_id, funding)
        return intent

    def payment_status(self, payment_intent_id: str) -> dict:
        return self.http.request("GET", "payment_intents/" + _id(payment_intent_id, "pi"))

    def payout_status(self, payout_id: str, connected_account: str) -> dict:
        return self.http.request(
            "GET", "payouts/" + _id(payout_id, "po"), account=_id(connected_account, "acct")
        )

    def payout(self, settlement_id: str, *, idempotency_key: str) -> dict:
        """Transfer finalized net proceeds, then request the provider bank payout.

        Reservation is retained on any error. Stripe keys derive from the ledger
        settlement ID, so changing a client key cannot create a second payment.
        Stripe keys expire: the durable ledger must reject already completed or
        stale uncertain reservations until reconciled (never blindly re-POST).
        A pending payout is not paid. Call reconcile_payout to record later status.
        """
        _key(settlement_id, idempotency_key)
        net = self.ledger.reserve_settlement(settlement_id, idempotency_key)
        if net.settlement_id != settlement_id:
            raise ProtocolError("settlement mismatch")
        _money(net.amount, net.currency)
        account = _id(net.connected_account, "acct")
        transfer = self.http.request(
            "POST",
            "transfers",
            key=_key("transfer", settlement_id),
            data={
                "amount": net.amount,
                "currency": net.currency,
                "destination": account,
                "metadata[settlement_id]": settlement_id,
            },
        )
        _id(transfer.get("id"), "tr")
        if (
            type(transfer.get("amount")) is not int
            or transfer.get("amount") != net.amount
            or transfer.get("currency") != net.currency
            or transfer.get("destination") != account
            or transfer.get("metadata", {}).get("settlement_id") != settlement_id
        ):
            raise ProtocolError("transfer mismatch")
        payout = self.http.request(
            "POST",
            "payouts",
            key=_key("payout", settlement_id),
            account=account,
            data={
                "amount": net.amount,
                "currency": net.currency,
                "metadata[settlement_id]": settlement_id,
            },
        )
        self._record(net, transfer, payout)
        return payout

    def reconcile_payout(self, net: NetSettlement, transfer: dict, payout_id: str) -> dict:
        payout = self.payout_status(payout_id, net.connected_account)
        self._record(net, transfer, payout)
        return payout

    def _record(self, net: NetSettlement, transfer: dict, payout: dict) -> None:
        _id(payout.get("id"), "po")
        if (
            type(payout.get("amount")) is not int
            or payout.get("amount") != net.amount
            or payout.get("currency") != net.currency
            or payout.get("status") not in {"pending", "in_transit", "paid", "failed", "canceled"}
            or payout.get("metadata", {}).get("settlement_id") != net.settlement_id
        ):
            raise ProtocolError("payout mismatch")
        self.ledger.record_payout(net.settlement_id, transfer, payout)
