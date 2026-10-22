"""Opt-in escrow orchestration and a ledger-owned Stripe channel boundary.

All fiat amounts are integer minor units, without CC conversion. Provider account
bindings and mandate verification keys must come from trusted operator config.
Pending/unknown payouts fail closed: reconcile rather than automatically re-POST.
"""

from copy import deepcopy
from dataclasses import asdict
import hashlib
import re

from .core import ProtocolError
from .escrow import EscrowLedger, identifier, integer
from .journal import mutation
from .stripe_channel import Funding, NetSettlement
from .wire import canonical, sign
from .proofs import verify_result


class ClearingLedger(EscrowLedger):
    _state_fields = EscrowLedger._state_fields + ("_funding", "_deposits", "_outbox", "_paid_out")

    def __init__(self, currency="usd", *, provider_accounts, **kwargs):
        self._funding, self._deposits, self._outbox, self._paid_out = {}, {}, {}, 0
        self._provider_accounts = dict(provider_accounts)
        kwargs.setdefault("mandate_keys", {})
        super().__init__(currency, **kwargs)

    @mutation
    def open_account(self, account, amount=0):
        identifier(account)
        if account.startswith("@payout:"):
            raise ProtocolError("reserved account namespace")
        return super().open_account(account, amount)

    @mutation
    def create(self, transaction_id, buyer, provider, amount, fee=0, *, unit="request", rate=1):
        for party in (buyer, provider):
            identifier(party)
            if party.startswith("@payout:"):
                raise ProtocolError("reserved account cannot trade")
        return super().create(transaction_id, buyer, provider, amount, fee, unit=unit, rate=rate)

    def bind_funding(self, funding, key):
        self._bind_funding(asdict(funding), key)
        return funding

    @mutation
    def _bind_funding(self, funding, key):
        identifier(key)
        record = self.get(funding["escrow_id"])
        if (
            funding["buyer"] != record["buyer"]
            or funding["currency"] != self.currency
            or funding["amount"] != record["budget"] + record["fee_limit"]
        ):
            raise ProtocolError("funding mismatch")
        bound = self._funding.get(funding["escrow_id"])
        value = dict(funding=funding, key=key)
        if bound is not None and bound != value:
            raise ProtocolError("idempotency key conflict")
        for other_id, other in self._funding.items():
            if (
                other_id != funding["escrow_id"]
                and other["key"] == key
                and other["funding"]["buyer"] == funding["buyer"]
            ):
                raise ProtocolError("idempotency key conflict")
        self._funding[funding["escrow_id"]] = deepcopy(value)

    def credit_escrow(self, payment_intent_id, funding):
        self._credit_escrow(payment_intent_id, asdict(funding))

    @mutation
    def _credit_escrow(self, payment_intent_id, funding):
        if payment_intent_id in self._deposits:
            if self._deposits[payment_intent_id] != funding:
                raise ProtocolError("deposit conflict")
            return
        tx = funding["escrow_id"]
        if self._funding.get(tx, {}).get("funding") != funding:
            raise ProtocolError("unbound deposit")
        record = self.get(tx)
        if record["state"] != "QUOTE_REQUESTED":
            raise ProtocolError("escrow already funded")
        self._supply = integer(self._supply + funding["amount"])
        self._balances[funding["buyer"]] += funding["amount"]
        self.transition(tx, "QUOTE_ACCEPTED")
        self._deposits[payment_intent_id] = deepcopy(funding)

    @mutation
    def transition(self, transaction_id, target, *, amount=None, fee=0):
        if transaction_id in self._outbox:
            raise ProtocolError("payout reserved; external reconciliation required")
        return super().transition(transaction_id, target, amount=amount, fee=fee)

    def reserve_settlement(self, settlement_id, key):
        return NetSettlement(**self._reserve_settlement(settlement_id, key))

    @mutation
    def _reserve_settlement(self, settlement_id, key):
        identifier(key)
        if settlement_id in self._outbox:
            raise ProtocolError("payout already reserved; reconcile without re-POST")
        record = self.get(settlement_id)
        if record["state"] not in {"SETTLED", "SLASHED"} or record["amount"] <= 0:
            raise ProtocolError("final positive settlement required")
        account = self._provider_accounts.get(record["provider"])
        if not isinstance(account, str) or not re.fullmatch(r"acct_[A-Za-z0-9]+", account):
            raise ProtocolError("unknown provider account")
        if self._balances[record["provider"]] < record["amount"]:
            raise ProtocolError("insufficient credit")
        net = asdict(
            NetSettlement(
                settlement_id, record["provider"], account, record["amount"], self.currency
            )
        )
        self._balances[record["provider"]] -= record["amount"]
        self._balances["@payout:" + settlement_id] = record["amount"]
        self._outbox[settlement_id] = dict(net=net, key=key, transfer=None, payout=None)
        return deepcopy(net)

    @mutation
    def record_payout(self, settlement_id, transfer, payout):
        row = self._outbox.get(settlement_id)
        if row is None:
            raise ProtocolError("unknown payout reservation")
        net = row["net"]
        for item in (transfer, payout):
            if (
                type(item.get("amount")) is not int
                or item.get("amount") != net["amount"]
                or item.get("currency") != net["currency"]
                or item.get("metadata", {}).get("settlement_id") != settlement_id
            ):
                raise ProtocolError("payout allocation mismatch")
        for item, prefix in ((transfer, "tr"), (payout, "po")):
            if not isinstance(item.get("id"), str) or not re.fullmatch(
                prefix + r"_[A-Za-z0-9]+", item["id"]
            ):
                raise ProtocolError("invalid payout identity")
        if transfer.get("destination") != net["connected_account"]:
            raise ProtocolError("payout destination mismatch")
        if payout.get("status") not in {"pending", "in_transit", "paid", "failed", "canceled"}:
            raise ProtocolError("unknown payout status")
        if row["payout"] is not None:
            if row["payout"]["id"] != payout["id"] or row["transfer"]["id"] != transfer["id"]:
                raise ProtocolError("payout identity conflict")
            if row["payout"]["status"] == "paid":
                if row["payout"] != payout or row["transfer"] != transfer:
                    raise ProtocolError("paid payout cannot regress")
                return
        if payout["status"] == "paid":
            self._balances["@payout:" + settlement_id] -= net["amount"]
            self._supply -= net["amount"]
            self._paid_out += net["amount"]
        row.update(transfer=deepcopy(transfer), payout=deepcopy(payout))

    def payout_record(self, transaction_id):
        with self._lock:
            return deepcopy(self._outbox.get(transaction_id))


class EscrowWorkflow:
    def __init__(self, ledger):
        self.ledger = ledger

    def prepare(self, quote, mandate, agent, capability):
        self.ledger.prepare_authorized(quote, mandate, agent, capability)

    def execute(
        self,
        transaction_id,
        result,
        units,
        *,
        provider_key,
        provider_key_id,
        provider_keys,
        algorithm="Ed25519",
        dispute=False,
        award=None,
        fee=0,
    ):
        ledger = self.ledger
        ledger.start_task(transaction_id)
        result_hash = hashlib.sha256(canonical(result)).hexdigest()
        proof = sign(
            {"transaction_id": transaction_id, "result_hash": result_hash},
            provider_key,
            provider_key_id,
            algorithm,
            domain="result",
        )
        verify_result(result, proof, transaction_id, provider_keys)
        ledger.meter(transaction_id, units, result_hash)
        ledger.transition(transaction_id, "RESULT_DELIVERED")
        ledger.transition(transaction_id, "PROOF_VERIFIED")
        if dispute:
            ledger.transition(transaction_id, "DISPUTED")
        ledger.transition(
            transaction_id, "SETTLED", amount=units if award is None else award, fee=fee
        )
        return {"result": result, "proof": proof, "transaction": ledger.get(transaction_id)}
