"""Net settlement: hash-chained off-ledger metering, one settlement receipt.

The wedge this solves: per-request settlement breaks down for micro-priced
agent services — when the settlement cost of a rail exceeds the price of a
single call, the economics invert. The structural fix is a clearing channel:

    open      buyer deposits N credits into escrow once
    meter     each micro-task appends a signed UsageRecord to a hash chain
              (tamper-evident: every record commits to the previous hash)
    settle    one net transfer: provider receives the metered total, buyer
              receives the unused deposit, the protocol fee is charged once

100 tasks at 1 credit each = 1 escrow hold + 1 settlement instead of 100
settlements. The hash chain plus the final signed receipt give both parties
(and any rail adapter underneath) a verifiable audit trail of exactly what
was consumed.

Reuses existing primitives: the deposit is a normal `Transaction` held in
`EscrowLedger`, and settlement is `split_escrow` — provider share = net
total, buyer share = remainder.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from .clearing import ClearingService
from .core import (
    ProtocolError,
    SettlementCredit,
    Transaction,
    TransactionState,
)

GENESIS_HASH = "0" * 64


def _canonical_hash(payload: dict[str, object]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class UsageRecord:
    sequence: int
    capability: str
    amount: int  # credits for this micro-task
    payload_hash: str  # hash of the task input/output pair
    prev_hash: str
    recorded_at: str

    def record_hash(self) -> str:
        return _canonical_hash(
            {
                "sequence": self.sequence,
                "capability": self.capability,
                "amount": self.amount,
                "payload_hash": self.payload_hash,
                "prev_hash": self.prev_hash,
                "recorded_at": self.recorded_at,
            }
        )

    def to_json(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "capability": self.capability,
            "amount": self.amount,
            "payload_hash": self.payload_hash,
            "prev_hash": self.prev_hash,
            "recorded_at": self.recorded_at,
            "record_hash": self.record_hash(),
        }


class ChannelState(str, Enum):
    OPEN = "OPEN"
    SETTLED = "SETTLED"
    DISPUTED = "DISPUTED"


@dataclass
class NettingChannel:
    buyer: str
    provider: str
    deposit: int
    fee: int
    transaction: Transaction
    channel_id: str = field(default_factory=lambda: f"chan_{uuid4().hex}")
    records: list[UsageRecord] = field(default_factory=list)
    state: ChannelState = ChannelState.OPEN
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # -- metering -----------------------------------------------------------
    def meter(self, capability: str, amount: int, payload_hash: str) -> UsageRecord:
        if self.state is not ChannelState.OPEN:
            raise ProtocolError(f"channel not open: {self.state.value}")
        if amount <= 0:
            raise ProtocolError("metered amount must be positive")
        if self.net_total() + amount > self.spendable():
            raise ProtocolError("channel deposit exhausted")
        prev = self.records[-1].record_hash() if self.records else GENESIS_HASH
        record = UsageRecord(
            sequence=len(self.records),
            capability=capability,
            amount=amount,
            payload_hash=payload_hash,
            prev_hash=prev,
            recorded_at=datetime.now(timezone.utc).isoformat(),
        )
        self.records.append(record)
        return record

    def net_total(self) -> int:
        return sum(record.amount for record in self.records)

    def spendable(self) -> int:
        return self.deposit - self.fee

    def chain_head(self) -> str:
        return self.records[-1].record_hash() if self.records else GENESIS_HASH

    def verify_chain(self) -> bool:
        prev = GENESIS_HASH
        for index, record in enumerate(self.records):
            if record.sequence != index or record.prev_hash != prev:
                return False
            prev = record.record_hash()
        return True


class NettingService:
    """Channel lifecycle on top of a ClearingService."""

    def __init__(self, clearing: ClearingService) -> None:
        self.clearing = clearing
        self.channels: dict[str, NettingChannel] = {}

    # -- lifecycle ------------------------------------------------------------
    def open_channel(self, buyer: str, provider: str, deposit: int, currency: str = "CC") -> NettingChannel:
        if deposit <= 0:
            raise ProtocolError("deposit must be positive")
        fee = self.clearing.fees.policy_for("netting.channel").fee_for(
            SettlementCredit(deposit, currency)
        )
        transaction = Transaction(
            sender=buyer,
            receiver=provider,
            amount=SettlementCredit(deposit - fee.amount, currency),
            fee=fee,
            capability="netting.channel",
            state=TransactionState.QUOTE_ACCEPTED,
        )
        transaction.transition(TransactionState.TASK_SUBMITTED)
        self.clearing.ledger.hold(transaction)
        self.clearing._transactions[transaction.transaction_id] = transaction

        channel = NettingChannel(
            buyer=buyer,
            provider=provider,
            deposit=deposit,
            fee=fee.amount,
            transaction=transaction,
        )
        self.channels[channel.channel_id] = channel
        return channel

    def settle(self, channel_id: str) -> dict[str, object]:
        """One net transfer closes the channel; returns a signed receipt."""
        channel = self._get(channel_id)
        if channel.state is not ChannelState.OPEN:
            raise ProtocolError(f"channel not open: {channel.state.value}")
        if not channel.verify_chain():
            raise ProtocolError("usage chain integrity check failed")

        net = channel.net_total()
        tx = channel.transaction
        tx.transition(TransactionState.TASK_RUNNING)
        tx.transition(TransactionState.RESULT_DELIVERED)
        tx.transition(TransactionState.PROOF_VERIFIED)
        tx.transition(TransactionState.DISPUTED)  # gateway state for split
        self.clearing.ledger.split_escrow(tx, provider_amount=net)

        channel.state = ChannelState.SETTLED
        receipt = self.clearing.signer.sign(
            {
                "receipt_id": f"netrcpt_{channel.channel_id}",
                "channel_id": channel.channel_id,
                "buyer": channel.buyer,
                "provider": channel.provider,
                "deposit": channel.deposit,
                "net_to_provider": net,
                "refunded_to_buyer": channel.deposit - channel.fee - net,
                "protocol_fee": channel.fee,
                "tasks_metered": len(channel.records),
                "chain_head": channel.chain_head(),
                "settled_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self.clearing.receipts[str(receipt["receipt_id"])] = receipt
        return receipt

    def dispute(self, channel_id: str) -> NettingChannel:
        """Freeze the channel; escrow stays held until resolution through
        ClearingService.resolve_dispute on the channel's transaction."""
        channel = self._get(channel_id)
        if channel.state is not ChannelState.OPEN:
            raise ProtocolError(f"channel not open: {channel.state.value}")
        channel.state = ChannelState.DISPUTED
        tx = channel.transaction
        tx.transition(TransactionState.TASK_RUNNING)
        tx.transition(TransactionState.DISPUTED)
        return channel

    # -- analytics -------------------------------------------------------------
    def settlement_savings(self, channel_id: str, per_settlement_cost: float) -> dict[str, object]:
        """Quantify the wedge: cost of per-task settlement vs one net settlement."""
        channel = self._get(channel_id)
        tasks = len(channel.records)
        return {
            "tasks": tasks,
            "per_task_settlement_cost": per_settlement_cost * tasks,
            "net_settlement_cost": per_settlement_cost,
            "settlements_avoided": max(tasks - 1, 0),
            "cost_reduction_factor": tasks if tasks else 0,
        }

    def _get(self, channel_id: str) -> NettingChannel:
        channel = self.channels.get(channel_id)
        if channel is None:
            raise ProtocolError("unknown channel")
        return channel
