"""Commercial clearing layer: escrow, protocol fees, disputes, events.

This module turns the protocol sketch into an economically real clearing
flow. The base `Ledger.settle()` moves credits instantly and `refund()`
only changes state — money never moves back. Real clearing requires:

    hold     buyer credits locked in escrow when the task is submitted
    release  escrow -> provider (minus protocol fee) after proof verifies
    refund   escrow -> buyer when a dispute resolves in the buyer's favor
    slash    escrow -> fee pool when the provider acted in bad faith
    split    partial resolutions divide escrow between both parties

`FeePolicy` is the first commercial engine: a basis-point protocol fee
(plus optional flat and minimum components) collected into the fee pool
on every release — the "marketplace transaction fee" described in
COMMERCIALIZATION.md, as code.

`ClearingService` assembles escrow + fees + signed receipts + events into
the unit a hosted product actually sells.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from .core import (
    Ledger,
    ProtocolError,
    Quote,
    SettlementCredit,
    SpendingMandate,
    TaskResult,
    Transaction,
    TransactionState,
)

# ---------------------------------------------------------------------------
# Fee engine
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeePolicy:
    """Protocol fee: `bps` basis points + `flat`, floored at `minimum`.

    Example: FeePolicy(bps=250, flat=1) on a 100 CC transaction
    charges 2.5 + 1 = 3 CC (integer credits round down, then floor).
    """

    bps: int = 0
    flat: int = 0
    minimum: int = 0
    currency: str = "CC"

    def __post_init__(self) -> None:
        if self.bps < 0 or self.flat < 0 or self.minimum < 0:
            raise ProtocolError("fee components must be non-negative")
        if self.bps > 10_000:
            raise ProtocolError("fee bps cannot exceed 10000 (100%)")

    def fee_for(self, amount: SettlementCredit) -> SettlementCredit:
        if amount.currency != self.currency:
            raise ProtocolError("fee policy currency mismatch")
        fee = amount.amount * self.bps // 10_000 + self.flat
        fee = max(fee, self.minimum)
        if fee >= amount.amount and amount.amount > 0:
            raise ProtocolError("fee would consume the entire settlement amount")
        return SettlementCredit(fee, self.currency)


class FeeSchedule:
    """Per-capability overrides on top of a default policy."""

    def __init__(self, default: FeePolicy | None = None) -> None:
        self.default = default or FeePolicy()
        self._overrides: dict[str, FeePolicy] = {}

    def set_capability_fee(self, capability: str, policy: FeePolicy) -> None:
        self._overrides[capability] = policy

    def policy_for(self, capability: str) -> FeePolicy:
        return self._overrides.get(capability, self.default)


# ---------------------------------------------------------------------------
# Escrow ledger
# ---------------------------------------------------------------------------


def _synchronized(method):
    """Run a ledger-mutating method under self._lock (re-entrant)."""
    import functools

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class EscrowLedger(Ledger):
    """Ledger with a real escrow pool. Zero-sum across balances + escrow + fees."""

    def __init__(self) -> None:
        super().__init__()
        self.escrow: dict[str, int] = {}  # transaction_id -> held amount
        self._lock = threading.RLock()

    # -- invariants ---------------------------------------------------------
    def escrow_total(self) -> int:
        return sum(self.escrow.values())

    def snapshot(self) -> dict[str, object]:
        snap = super().snapshot()
        snap["escrow"] = dict(self.escrow)
        snap["escrow_total"] = self.escrow_total()
        return snap

    def verify_zero_sum(self, before: dict[str, object] | None = None) -> bool:
        if before is None:
            total = sum(self.balances.values()) + self.fee_pool + self.escrow_total()
            return total == self.total_supply
        prev_balances = before.get("balances")
        prev_fee = before.get("fee_pool")
        prev_escrow = before.get("escrow_total", 0)
        if not isinstance(prev_balances, dict) or not isinstance(prev_fee, int):
            raise ProtocolError("invalid ledger snapshot")
        before_total = sum(prev_balances.values()) + prev_fee + int(prev_escrow)
        after_total = sum(self.balances.values()) + self.fee_pool + self.escrow_total()
        return before_total == after_total

    # -- escrow lifecycle ---------------------------------------------------
    @_synchronized
    def hold(self, transaction: Transaction) -> None:
        """Lock buyer funds (amount + fee) when the task is submitted."""
        if transaction.transaction_id in self.escrow:
            raise ProtocolError("funds already held for transaction")
        total = transaction.amount.amount + transaction.fee.amount
        if self.balance_of(transaction.sender) < total:
            raise ProtocolError("insufficient credit")
        before = self.snapshot()
        self.balances[transaction.sender] = self.balance_of(transaction.sender) - total
        self.escrow[transaction.transaction_id] = total
        if not self.verify_zero_sum(before):
            raise ProtocolError("ledger invariant failed on hold")

    @_synchronized
    def release(self, transaction: Transaction) -> None:
        """Escrow -> provider (amount) + fee pool (fee). Marks SETTLED."""
        held = self._take(transaction)
        before = self.snapshot()
        before["escrow_total"] = before["escrow_total"] + held  # type: ignore[operator]
        self.balances[transaction.receiver] = (
            self.balance_of(transaction.receiver) + transaction.amount.amount
        )
        self.fee_pool += transaction.fee.amount
        transaction.state = TransactionState.SETTLED
        transaction.settled_at = datetime.now(timezone.utc)
        self.transactions.append(transaction)
        if not self.verify_zero_sum(before):
            raise ProtocolError("ledger invariant failed on release")

    @_synchronized
    def refund_escrow(self, transaction: Transaction) -> None:
        """Escrow -> buyer in full. Marks REFUNDED."""
        held = self._take(transaction)
        before = self.snapshot()
        before["escrow_total"] = before["escrow_total"] + held  # type: ignore[operator]
        self.balances[transaction.sender] = self.balance_of(transaction.sender) + held
        transaction.transition(TransactionState.REFUNDED)
        if not self.verify_zero_sum(before):
            raise ProtocolError("ledger invariant failed on refund")

    @_synchronized
    def slash_escrow(self, transaction: Transaction) -> None:
        """Escrow -> fee pool (provider penalized, buyer compensated separately
        in richer deployments). Marks SLASHED."""
        held = self._take(transaction)
        before = self.snapshot()
        before["escrow_total"] = before["escrow_total"] + held  # type: ignore[operator]
        self.fee_pool += held
        transaction.transition(TransactionState.SLASHED)
        if not self.verify_zero_sum(before):
            raise ProtocolError("ledger invariant failed on slash")

    @_synchronized
    def split_escrow(self, transaction: Transaction, provider_amount: int) -> None:
        """Partial resolution: provider gets `provider_amount`, buyer gets the
        rest, protocol fee still applies to the provider share's transaction fee.
        Marks SETTLED (partial settlements are settlements with a dispute note)."""
        held = self._take(transaction)
        if provider_amount < 0 or provider_amount > transaction.amount.amount:
            raise ProtocolError("provider share out of range")
        before = self.snapshot()
        before["escrow_total"] = before["escrow_total"] + held  # type: ignore[operator]
        buyer_back = held - provider_amount - transaction.fee.amount
        self.balances[transaction.receiver] = (
            self.balance_of(transaction.receiver) + provider_amount
        )
        self.balances[transaction.sender] = self.balance_of(transaction.sender) + buyer_back
        self.fee_pool += transaction.fee.amount
        transaction.state = TransactionState.SETTLED
        transaction.settled_at = datetime.now(timezone.utc)
        self.transactions.append(transaction)
        if not self.verify_zero_sum(before):
            raise ProtocolError("ledger invariant failed on split")

    def _take(self, transaction: Transaction) -> int:
        held = self.escrow.pop(transaction.transaction_id, None)
        if held is None:
            raise ProtocolError("no funds held for transaction")
        return held


# ---------------------------------------------------------------------------
# Disputes
# ---------------------------------------------------------------------------


@dataclass
class Dispute:
    transaction_id: str
    raised_by: str
    reason: str
    evidence: dict[str, object] = field(default_factory=dict)
    dispute_id: str = field(default_factory=lambda: f"dsp_{uuid4().hex}")
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolution: str | None = None  # refund | slash | settle | split
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    provider_amount: int | None = None  # for split

    def to_json(self) -> dict[str, object]:
        return {
            "dispute_id": self.dispute_id,
            "transaction_id": self.transaction_id,
            "raised_by": self.raised_by,
            "reason": self.reason,
            "evidence": self.evidence,
            "opened_at": self.opened_at.isoformat(),
            "resolution": self.resolution,
            "resolved_by": self.resolved_by,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "provider_amount": self.provider_amount,
        }


# ---------------------------------------------------------------------------
# Events (webhook foundation)
# ---------------------------------------------------------------------------

EVENT_TRANSACTION_HELD = "transaction.held"
EVENT_RECEIPT_CREATED = "receipt.created"
EVENT_DISPUTE_OPENED = "dispute.opened"
EVENT_DISPUTE_RESOLVED = "dispute.resolved"

EventHandler = Callable[[str, dict[str, object]], None]


class EventBus:
    """Synchronous in-process bus. A hosted product replaces handlers with
    webhook delivery; the emit sites stay identical."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}
        self.history: list[tuple[str, dict[str, object]]] = []

    def subscribe(self, event: str, handler: EventHandler) -> None:
        self._handlers.setdefault(event, []).append(handler)

    def emit(self, event: str, payload: dict[str, object]) -> None:
        self.history.append((event, payload))
        for handler in self._handlers.get(event, []):
            handler(event, payload)


# ---------------------------------------------------------------------------
# Receipt signing (core-level, stdlib HMAC; swap for ed25519 in production)
# ---------------------------------------------------------------------------


class ReceiptSigner:
    def __init__(self, secret: str = "dev_neuralclear_signing_secret") -> None:
        self._secret = secret.encode("utf-8")

    def _digest(self, receipt: dict[str, object]) -> str:
        body = {k: v for k, v in receipt.items() if k != "signature"}
        payload = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
        return hmac.new(self._secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()

    def sign(self, receipt: dict[str, object]) -> dict[str, object]:
        signed = dict(receipt)
        signed["signature"] = f"hmac-sha256:{self._digest(receipt)}"
        return signed

    def verify(self, receipt: dict[str, object]) -> bool:
        sig = receipt.get("signature")
        if not isinstance(sig, str) or not sig.startswith("hmac-sha256:"):
            return False
        return hmac.compare_digest(sig.split(":", 1)[1], self._digest(receipt))


# ---------------------------------------------------------------------------
# Clearing service — the commercial unit
# ---------------------------------------------------------------------------

TaskRunner = Callable[[], TaskResult]


class ClearingService:
    """Escrow + fees + signed receipts + events, assembled.

    This is the object a hosted NeuralClear deployment charges for:
    every cleared transaction pays the protocol fee into `ledger.fee_pool`.
    """

    def __init__(
        self,
        ledger: EscrowLedger | None = None,
        fees: FeeSchedule | None = None,
        signer: ReceiptSigner | None = None,
        events: EventBus | None = None,
    ) -> None:
        self.ledger = ledger or EscrowLedger()
        self.fees = fees or FeeSchedule()
        self.signer = signer or ReceiptSigner()
        self.events = events or EventBus()
        self.disputes: dict[str, Dispute] = {}
        self._transactions: dict[str, Transaction] = {}
        self.receipts: dict[str, dict[str, object]] = {}

    # -- main flow ----------------------------------------------------------
    def clear(
        self,
        buyer_owner: str,
        buyer_agent: str,
        quote: Quote,
        run: TaskRunner,
        mandate: SpendingMandate | None = None,
    ) -> dict[str, object]:
        """Full commercial clearing of one task. Returns a signed receipt."""
        if quote.is_expired():
            raise ProtocolError("quote expired")
        fee = self.fees.policy_for(quote.capability).fee_for(quote.settlement_price)

        if mandate is not None:
            charged = SettlementCredit(
                quote.settlement_price.amount + fee.amount, quote.settlement_price.currency
            )
            mandate.assert_allows(quote.capability, charged)
            spent = self.ledger.get_daily_spend(
                mandate.agent, mandate.owner, datetime.now(timezone.utc).date()
            )
            mandate.assert_daily_budget(spent, charged)

        transaction = Transaction(
            sender=buyer_owner,
            receiver=quote.provider,
            amount=quote.settlement_price,
            fee=fee,
            capability=quote.capability,
            quote_id=quote.quote_id,
            authorized_agent=buyer_agent,
            state=TransactionState.QUOTE_ACCEPTED,
        )
        self._transactions[transaction.transaction_id] = transaction

        transaction.transition(TransactionState.TASK_SUBMITTED)
        self.ledger.hold(transaction)
        self.events.emit(
            EVENT_TRANSACTION_HELD,
            {"transaction_id": transaction.transaction_id, "held": self.ledger_held(transaction)},
        )

        transaction.transition(TransactionState.TASK_RUNNING)
        try:
            result = run()
        except Exception as exc:
            # provider crashed mid-execution -> never strand buyer funds
            transaction.transition(TransactionState.DISPUTED)
            self.ledger.refund_escrow(transaction)
            raise ProtocolError(f"task execution failed; escrow refunded: {exc}") from exc
        transaction.transition(TransactionState.RESULT_DELIVERED)

        if not result.proof.verify():
            # proof failure -> automatic full refund, no fee charged
            transaction.transition(TransactionState.DISPUTED)
            self.ledger.refund_escrow(transaction)
            raise ProtocolError("proof verification failed; escrow refunded")

        transaction.transition(TransactionState.PROOF_VERIFIED)
        self.ledger.release(transaction)

        receipt = self._build_receipt(transaction, result)
        self.receipts[receipt["receipt_id"]] = receipt  # type: ignore[index]
        self.events.emit(EVENT_RECEIPT_CREATED, receipt)
        return receipt

    # -- disputes -----------------------------------------------------------
    def open_dispute(
        self, transaction_id: str, raised_by: str, reason: str, evidence: dict[str, object] | None = None
    ) -> Dispute:
        transaction = self._get_tx(transaction_id)
        # disputes on settled transactions are recorded; escrow-stage disputes freeze funds
        if transaction.state != TransactionState.DISPUTED:
            transaction.transition(TransactionState.DISPUTED)
        dispute = Dispute(
            transaction_id=transaction_id,
            raised_by=raised_by,
            reason=reason,
            evidence=evidence or {},
        )
        self.disputes[dispute.dispute_id] = dispute
        self.events.emit(EVENT_DISPUTE_OPENED, dispute.to_json())
        return dispute

    def resolve_dispute(
        self,
        dispute_id: str,
        resolution: str,
        resolved_by: str,
        provider_amount: int | None = None,
    ) -> Dispute:
        dispute = self.disputes.get(dispute_id)
        if dispute is None:
            raise ProtocolError("unknown dispute")
        if dispute.resolution is not None:
            raise ProtocolError("dispute already resolved")
        transaction = self._get_tx(dispute.transaction_id)

        if resolution == "refund":
            self.ledger.refund_escrow(transaction)
        elif resolution == "slash":
            self.ledger.slash_escrow(transaction)
        elif resolution == "split":
            if provider_amount is None:
                raise ProtocolError("split resolution requires provider_amount")
            self.ledger.split_escrow(transaction, provider_amount)
        elif resolution == "settle":
            self.ledger.release(transaction)
        else:
            raise ProtocolError(f"unknown resolution: {resolution}")

        dispute.resolution = resolution
        dispute.resolved_by = resolved_by
        dispute.resolved_at = datetime.now(timezone.utc)
        dispute.provider_amount = provider_amount
        self.events.emit(EVENT_DISPUTE_RESOLVED, dispute.to_json())
        return dispute

    # -- helpers ------------------------------------------------------------
    def ledger_held(self, transaction: Transaction) -> int:
        return self.ledger.escrow.get(transaction.transaction_id, 0)

    def _get_tx(self, transaction_id: str) -> Transaction:
        transaction = self._transactions.get(transaction_id)
        if transaction is None:
            raise ProtocolError("unknown transaction")
        return transaction

    def _build_receipt(self, transaction: Transaction, result: TaskResult) -> dict[str, object]:
        receipt = {
            "receipt_id": f"rcpt_{transaction.transaction_id}",
            "transaction_id": transaction.transaction_id,
            "buyer": transaction.sender,
            "provider": transaction.receiver,
            "capability": transaction.capability,
            "amount": transaction.amount.amount,
            "fee": transaction.fee.amount,
            "currency": transaction.amount.currency,
            "proof": result.proof.to_json(),
            "resource_usage": [item.to_json() for item in result.resource_usage],
            "settled_at": transaction.settled_at.isoformat() if transaction.settled_at else None,
        }
        return self.signer.sign(receipt)
