"""Opt-in escrow clearing profile; legacy Ledger/SDK behavior is unchanged.

One instance is one currency and a single-process reference ledger. Dispute
resolutions are submitted by a trusted caller (arbitrator authorization is an
application responsibility). Monetary state changes are validated before commit.
"""

from __future__ import annotations

from copy import deepcopy
from threading import RLock
import time

from .core import ALLOWED_TRANSITIONS, ProtocolError, TransactionState as State
from .wire import PROFILE, ZERO_HASH, digest, sign
from .journal import Journal, mutation

MAX_INTEGER = 2**53 - 1


def integer(value: int) -> int:
    if type(value) is not int or not 0 <= value <= MAX_INTEGER:
        raise ProtocolError("expected non-negative safe integer")
    return value


def identifier(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or not value.isascii()
        or not all(33 <= ord(char) <= 126 for char in value)
    ):
        raise ProtocolError("expected printable ASCII identifier")
    return value


class EscrowLedger:
    _state_fields = (
        "_balances",
        "_escrows",
        "_fee_pool",
        "_supply",
        "_chains",
        "_mandates",
        "_revoked",
        "_authorizations",
    )

    def __init__(
        self,
        currency: str = "CC",
        *,
        journal_path=None,
        checkpoint=None,
        mandate_keys=None,
        clock=time.time,
        wait_for_writer=False,
    ) -> None:
        self.currency = identifier(currency)
        self._balances = {}
        self._escrows = {}
        self._fee_pool = 0
        self._supply = 0
        self._chains = {}
        self._lock = RLock()
        self._mandates, self._revoked, self._authorizations = {}, {}, {}
        self._mandate_keys = deepcopy(mandate_keys)
        self._clock, self._replay_time = clock, None
        self._journal = None
        self._broken = False
        self._in_mutation = False
        if journal_path is not None:
            if checkpoint is None:
                raise ProtocolError("trusted checkpoint required for persistence")
            self._journal = Journal(
                journal_path, checkpoint, currency, self._replay, wait=wait_for_writer
            )

    def _replay(self, event):
        method = getattr(self, event["method"], None)
        if not getattr(method, "journal_mutation", False):
            raise ProtocolError("unknown journal operation")
        self._replay_time = integer(event["at"])
        try:
            method(*event["args"], **event["kwargs"])
        finally:
            self._replay_time = None

    @mutation
    def prepare_authorized(self, quote, mandate, agent, capability):
        required = {"transaction_id", "buyer", "provider", "amount"}
        if (
            not isinstance(quote, dict)
            or not required <= set(quote)
            or set(quote) - required - {"fee", "valid_until"}
        ):
            raise ProtocolError("invalid quote fields")
        if "valid_until" in quote and self._event_time >= integer(quote["valid_until"]):
            raise ProtocolError("quote expired")
        self.register_mandate(mandate)
        self.create(
            quote["transaction_id"],
            quote["buyer"],
            quote["provider"],
            quote["amount"],
            quote.get("fee", 0),
        )
        self.authorize(quote["transaction_id"], mandate["mandate_id"], agent, capability)

    @mutation
    def start_task(self, transaction_id):
        self.transition(transaction_id, "TASK_SUBMITTED")
        return self.transition(transaction_id, "TASK_RUNNING")

    @mutation
    def register_mandate(self, mandate):
        from .mandates import validate_mandate

        validate_mandate(mandate, self._mandate_keys or {})
        mid = mandate["mandate_id"]
        if mid in self._mandates and self._mandates[mid] != mandate:
            raise ProtocolError("mandate id conflict")
        self._mandates[mid] = deepcopy(mandate)

    @mutation
    def revoke_mandate(self, mandate_id):
        # Trusted owner/admin operation; never exposed as an unauthenticated route.
        if mandate_id not in self._mandates:
            raise ProtocolError("unknown mandate")
        self._revoked[mandate_id] = self._event_time

    @mutation
    def authorize(self, transaction_id, mandate_id, agent, capability):
        record = self.get(transaction_id)
        if record["state"] != "QUOTE_REQUESTED" or transaction_id in self._authorizations:
            raise ProtocolError("authorization already bound")
        self._authorizations[transaction_id] = dict(
            mandate_id=mandate_id,
            agent=agent,
            capability=capability,
            reserved=0,
            spent=0,
            day=self._event_time // 86400,
        )
        self._check_authority(transaction_id)

    def _check_authority(self, transaction_id):
        from .mandates import validate_mandate

        if self._mandate_keys is None and transaction_id not in self._authorizations:
            return None
        auth = self._authorizations.get(transaction_id)
        if auth is None:
            raise ProtocolError("mandate required")
        mandate = self._mandates.get(auth["mandate_id"])
        if mandate is None:
            raise ProtocolError("unknown mandate")
        validate_mandate(mandate, self._mandate_keys or {})
        record = self._escrows[transaction_id]
        if auth["mandate_id"] in self._revoked:
            raise ProtocolError("mandate revoked")
        if self._event_time >= mandate["valid_until"]:
            raise ProtocolError("mandate expired")
        if mandate["currency"] != self.currency:
            raise ProtocolError("mandate currency mismatch")
        if auth["capability"] not in mandate["allowed_capabilities"]:
            raise ProtocolError("capability not allowed")
        if mandate["owner"] != record["buyer"] or mandate["agent"] != auth["agent"]:
            raise ProtocolError("mandate context mismatch")
        amount = record["budget"] + record["fee_limit"]
        if amount > mandate["max_per_task"]:
            raise ProtocolError("mandate per-task limit")
        if amount > mandate["requires_human_approval_above"]:
            raise ProtocolError("human approval required; issue a revised signed mandate")
        return mandate

    def _reserve_budget(self, transaction_id):
        mandate = self._check_authority(transaction_id)
        if mandate is None:
            return
        auth = self._authorizations[transaction_id]
        day = self._event_time // 86400
        peers = [
            a
            for tx, a in self._authorizations.items()
            if tx != transaction_id and a["mandate_id"] == auth["mandate_id"]
        ]
        amount = (
            self._escrows[transaction_id]["budget"] + self._escrows[transaction_id]["fee_limit"]
        )
        if sum(a["reserved"] + a["spent"] for a in peers) + amount > mandate["max_total"]:
            raise ProtocolError("mandate total limit")
        if (
            sum(a["reserved"] + a["spent"] for a in peers if a["day"] == day) + amount
            > mandate["max_daily"]
        ):
            raise ProtocolError("mandate daily limit")
        auth.update(day=day, reserved=amount)

    def mandate_usage(self, mandate_id):
        with self._lock:
            entries = [a for a in self._authorizations.values() if a["mandate_id"] == mandate_id]
            return {
                "reserved": sum(a["reserved"] for a in entries),
                "spent": sum(a["spent"] for a in entries),
            }

    def close(self):
        with self._lock:
            if self._journal is not None:
                self._journal.close()
                self._broken = True

    @mutation
    def open_account(self, account: str, amount: int = 0) -> None:
        identifier(account)
        integer(amount)
        with self._lock:
            if account in self._balances:
                raise ProtocolError("account already exists")
            integer(self._supply + amount)
            self._balances[account] = amount
            self._supply += amount

    @mutation
    def create(
        self,
        transaction_id: str,
        buyer: str,
        provider: str,
        amount: int,
        fee: int = 0,
        *,
        unit: str = "request",
        rate: int = 1,
    ) -> dict:
        for value in (transaction_id, buyer, provider):
            identifier(value)
        integer(amount)
        integer(fee)
        integer(amount + fee)
        identifier(unit)
        integer(rate)
        with self._lock:
            if transaction_id in self._escrows:
                raise ProtocolError("duplicate transaction")
            if buyer == provider or buyer not in self._balances or provider not in self._balances:
                raise ProtocolError("invalid parties")
            self._escrows[transaction_id] = {
                "transaction_id": transaction_id,
                "buyer": buyer,
                "provider": provider,
                "currency": self.currency,
                "budget": amount,
                "fee_limit": fee,
                "state": State.QUOTE_REQUESTED.value,
                "held": 0,
                "amount": 0,
                "fee": 0,
                "funded": 0,
                "refund": 0,
                "revision": 0,
                "resolution": False,
                "history": [State.QUOTE_REQUESTED.value],
                "unit": unit,
                "rate": rate,
            }
            self._chains[transaction_id] = []
            return self.get(transaction_id)

    def get(self, transaction_id: str) -> dict:
        with self._lock:
            try:
                return deepcopy(self._escrows[transaction_id])
            except KeyError:
                raise ProtocolError("unknown escrow") from None

    @mutation
    def transition(
        self, transaction_id: str, target: str, *, amount: int | None = None, fee: int = 0
    ) -> dict:
        with self._lock:
            record = self.get(transaction_id)
            try:
                state, next_state = State(record["state"]), State(target)
            except (ValueError, TypeError):
                raise ProtocolError("unknown state") from None
            if next_state not in ALLOWED_TRANSITIONS[state]:
                raise ProtocolError("invalid transition")
            closing = next_state in {State.SETTLED, State.REFUNDED, State.SLASHED}
            if not closing and (amount is not None or fee != 0):
                raise ProtocolError("award only allowed on settlement/resolution")
            balances, fee_pool = dict(self._balances), self._fee_pool
            buyer, provider = record["buyer"], record["provider"]
            if next_state == State.QUOTE_ACCEPTED:
                self._reserve_budget(transaction_id)
                hold = record["budget"] + record["fee_limit"]
                if balances[buyer] < hold:
                    raise ProtocolError("insufficient credit")
                balances[buyer] -= hold
                record["held"] = record["funded"] = hold
            elif next_state == State.EXPIRED:
                balances[buyer] += record["held"]
                record["refund"] += record["held"]
                record["held"] = 0
            elif next_state == State.DISPUTED and state == State.SETTLED:
                # Re-freeze precisely the last allocation, never unrelated balances.
                if balances[provider] < record["amount"] or fee_pool < record["fee"]:
                    raise ProtocolError("insufficient funds to freeze settled allocation")
                balances[provider] -= record["amount"]
                fee_pool -= record["fee"]
                record["held"] = record["amount"] + record["fee"]
                record["amount"] = record["fee"] = 0
            elif closing:
                if next_state == State.REFUNDED:
                    if amount not in (None, 0) or fee != 0:
                        raise ProtocolError("refund must return all held funds")
                    amount = 0
                if amount is None:
                    raise ProtocolError("explicit net award required")
                integer(amount)
                integer(fee)
                if amount > sum(event["amount"] for event in self._chains[transaction_id]):
                    raise ProtocolError("award exceeds metered amount")
                if (
                    amount > record["budget"]
                    or fee > record["fee_limit"]
                    or amount + fee > record["held"]
                ):
                    raise ProtocolError("award exceeds escrow")
                balances[provider] += amount
                fee_pool += fee
                refund = record["held"] - amount - fee
                balances[buyer] += refund
                record.update(
                    amount=amount,
                    fee=fee,
                    held=0,
                    refund=record["refund"] + refund,
                    resolution=state == State.DISPUTED,
                )
            record["state"] = next_state.value
            if next_state in {
                State.TASK_SUBMITTED,
                State.TASK_RUNNING,
                State.RESULT_DELIVERED,
                State.PROOF_VERIFIED,
            }:
                self._check_authority(transaction_id)
            if transaction_id in self._authorizations and (closing or next_state == State.EXPIRED):
                self._authorizations[transaction_id].update(
                    reserved=0, spent=record["amount"] + record["fee"]
                )
            record["revision"] += 1
            record["history"].append(next_state.value)
            held_total = (
                sum(item["held"] for key, item in self._escrows.items() if key != transaction_id)
                + record["held"]
            )
            if (
                any(value < 0 for value in balances.values())
                or fee_pool < 0
                or sum(balances.values()) + fee_pool + held_total != self._supply
            ):
                raise ProtocolError("ledger invariant failed")
            self._balances, self._fee_pool = balances, fee_pool
            self._escrows[transaction_id] = record
            return deepcopy(record)

    @mutation
    def meter(self, transaction_id: str, units: int, result_hash: str) -> dict:
        import re

        integer(units)
        if not isinstance(result_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", result_hash):
            raise ProtocolError("invalid result hash")
        with self._lock:
            record = self.get(transaction_id)
            if record["state"] != State.TASK_RUNNING.value:
                raise ProtocolError("meter requires running task")
            self._check_authority(transaction_id)
            chain = self._chains[transaction_id]
            cost = integer(units * record["rate"])
            if sum(event["amount"] for event in chain) + cost > record["budget"]:
                raise ProtocolError("meter exceeds budget")
            event = {
                "transaction_id": transaction_id,
                "currency": self.currency,
                "seq": len(chain),
                "previous": chain[-1]["hash"] if chain else ZERO_HASH,
                "units": units,
                "unit": record["unit"],
                "rate": record["rate"],
                "amount": cost,
                "result_hash": result_hash,
            }
            event["hash"] = digest(event)
            chain.append(event)
            return deepcopy(event)

    def chain(self, transaction_id: str) -> list:
        with self._lock:
            self.get(transaction_id)
            return deepcopy(self._chains[transaction_id])

    def receipt(
        self, transaction_id: str, *, key: bytes, key_id: str, algorithm="HMAC-SHA256"
    ) -> dict:
        identifier(key_id)
        with self._lock:
            if self._broken:
                raise ProtocolError("journal unavailable; cannot attest state")
            record = self.get(transaction_id)
            if record["state"] not in {"SETTLED", "REFUNDED", "SLASHED", "EXPIRED"}:
                raise ProtocolError("unresolved escrow")
            chain = self._chains[transaction_id]
            body = {k: v for k, v in record.items() if k not in {"held", "resolution"}}
            body.update(
                profile=PROFILE,
                chain_length=len(chain),
                chain_head=chain[-1]["hash"] if chain else ZERO_HASH,
                result_hash=chain[-1]["result_hash"] if chain else ZERO_HASH,
                deltas={
                    "buyer": -(record["amount"] + record["fee"]),
                    "provider": record["amount"],
                    "fee_pool": record["fee"],
                    "escrow": 0,
                },
            )
            return sign(body, key, key_id, algorithm)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "balances": dict(self._balances),
                "fee_pool": self._fee_pool,
                "held": sum(item["held"] for item in self._escrows.values()),
                "total_supply": self._supply,
            }
