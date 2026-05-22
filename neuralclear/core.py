from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Iterable
from uuid import uuid4


class ProtocolError(ValueError):
    """Raised when a protocol invariant is violated."""


@dataclass(frozen=True)
class ResourceUnit:
    """Metered resource use such as tokens, GPU seconds, bandwidth, or storage."""

    amount: float
    unit: str

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ProtocolError("resource unit amount must be non-negative")
        if not self.unit:
            raise ProtocolError("resource unit must be set")

    def to_json(self) -> dict[str, float | str]:
        return {"amount": self.amount, "unit": self.unit}


@dataclass(frozen=True)
class SettlementCredit:
    """Settlement-denominated credit used by the clearing ledger."""

    amount: int
    currency: str = "CC"

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ProtocolError("settlement credit amount must be non-negative")
        if not self.currency:
            raise ProtocolError("settlement currency must be set")

    def to_json(self) -> dict[str, int | str]:
        return {"amount": self.amount, "currency": self.currency}


@dataclass(frozen=True)
class Capability:
    name: str
    resource_price: ResourceUnit
    settlement_price: SettlementCredit
    description: str = ""

    def to_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "resource_price": self.resource_price.to_json(),
            "settlement_price": self.settlement_price.to_json(),
        }


@dataclass
class AgentInfo:
    agent_id: str
    name: str
    endpoint: str
    public_key: str
    capabilities: list[Capability]
    reputation_score: float = 0.0

    def supports(self, capability: str) -> bool:
        return any(item.name == capability for item in self.capabilities)

    def quote_for(self, capability: str, ttl_seconds: int = 300) -> "Quote":
        for item in self.capabilities:
            if item.name == capability:
                return Quote(
                    provider=self.agent_id,
                    capability=capability,
                    resource_estimate=item.resource_price,
                    settlement_price=item.settlement_price,
                    expires_at=datetime.now(timezone.utc).timestamp() + ttl_seconds,
                )
        raise ProtocolError(f"agent {self.agent_id} does not support {capability}")

    def to_json(self) -> dict[str, object]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "endpoint": self.endpoint,
            "public_key": self.public_key,
            "capabilities": [item.to_json() for item in self.capabilities],
            "reputation_score": self.reputation_score,
        }


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentInfo] = {}

    def register(self, agent: AgentInfo) -> None:
        if agent.agent_id in self._agents:
            raise ProtocolError(f"agent already registered: {agent.agent_id}")
        self._agents[agent.agent_id] = agent

    def get(self, agent_id: str) -> AgentInfo:
        try:
            return self._agents[agent_id]
        except KeyError as exc:
            raise ProtocolError(f"unknown agent: {agent_id}") from exc

    def discover(self, capability: str) -> list[AgentInfo]:
        return [agent for agent in self._agents.values() if agent.supports(capability)]


@dataclass(frozen=True)
class SpendingMandate:
    owner: str
    agent: str
    allowed_capabilities: list[str]
    max_per_task: SettlementCredit
    max_daily: SettlementCredit
    valid_until: float
    requires_human_approval_above: SettlementCredit
    signature: str

    def assert_allows(self, capability: str, amount: SettlementCredit, now: float | None = None) -> None:
        current = now if now is not None else datetime.now(timezone.utc).timestamp()
        if current > self.valid_until:
            raise ProtocolError("spending mandate expired")
        if capability not in self.allowed_capabilities:
            raise ProtocolError(f"capability not allowed by mandate: {capability}")
        if amount.currency != self.max_per_task.currency:
            raise ProtocolError("mandate currency mismatch")
        if amount.amount > self.max_per_task.amount:
            raise ProtocolError("task amount exceeds mandate max_per_task")

    def assert_daily_budget(self, already_spent: SettlementCredit, next_amount: SettlementCredit) -> None:
        if already_spent.currency != self.max_daily.currency or next_amount.currency != self.max_daily.currency:
            raise ProtocolError("mandate currency mismatch")
        if already_spent.amount + next_amount.amount > self.max_daily.amount:
            raise ProtocolError("task amount exceeds mandate max_daily")

    def to_json(self) -> dict[str, object]:
        return {
            "owner": self.owner,
            "agent": self.agent,
            "allowed_capabilities": self.allowed_capabilities,
            "max_per_task": self.max_per_task.to_json(),
            "max_daily": self.max_daily.to_json(),
            "valid_until": self.valid_until,
            "requires_human_approval_above": self.requires_human_approval_above.to_json(),
            "signature": self.signature,
        }


class TransactionState(str, Enum):
    QUOTE_REQUESTED = "QUOTE_REQUESTED"
    QUOTE_ACCEPTED = "QUOTE_ACCEPTED"
    TASK_SUBMITTED = "TASK_SUBMITTED"
    TASK_RUNNING = "TASK_RUNNING"
    RESULT_DELIVERED = "RESULT_DELIVERED"
    PROOF_VERIFIED = "PROOF_VERIFIED"
    SETTLED = "SETTLED"
    DISPUTED = "DISPUTED"
    REFUNDED = "REFUNDED"
    SLASHED = "SLASHED"
    EXPIRED = "EXPIRED"


ALLOWED_TRANSITIONS: dict[TransactionState, set[TransactionState]] = {
    TransactionState.QUOTE_REQUESTED: {TransactionState.QUOTE_ACCEPTED, TransactionState.EXPIRED},
    TransactionState.QUOTE_ACCEPTED: {TransactionState.TASK_SUBMITTED, TransactionState.EXPIRED},
    TransactionState.TASK_SUBMITTED: {TransactionState.TASK_RUNNING, TransactionState.DISPUTED},
    TransactionState.TASK_RUNNING: {TransactionState.RESULT_DELIVERED, TransactionState.DISPUTED},
    TransactionState.RESULT_DELIVERED: {TransactionState.PROOF_VERIFIED, TransactionState.DISPUTED},
    TransactionState.PROOF_VERIFIED: {TransactionState.SETTLED, TransactionState.DISPUTED},
    TransactionState.SETTLED: {TransactionState.DISPUTED},
    TransactionState.DISPUTED: {TransactionState.REFUNDED, TransactionState.SLASHED, TransactionState.SETTLED},
    TransactionState.REFUNDED: set(),
    TransactionState.SLASHED: set(),
    TransactionState.EXPIRED: set(),
}


class ProofLevel(str, Enum):
    NONE = "NONE"
    SIGNED_RESULT = "SIGNED_RESULT"
    REPRODUCIBLE = "REPRODUCIBLE"
    TEE_ATTESTATION = "TEE_ATTESTATION"
    ZK_PROOF = "ZK_PROOF"


@dataclass(frozen=True)
class MockProof:
    """A development-only proof placeholder. This is not a real TEE proof."""

    proof_level: ProofLevel = ProofLevel.NONE
    statement: str = "mock proof for local demo only"
    signature: str = "mock-signature"

    def verify(self) -> bool:
        return self.proof_level == ProofLevel.NONE and self.signature == "mock-signature"

    def to_json(self) -> dict[str, str]:
        return {
            "proof_level": self.proof_level.value,
            "statement": self.statement,
            "signature": self.signature,
        }


@dataclass(frozen=True)
class SignedResultProof:
    """Reserved type for future signed-result verification."""

    proof_level: ProofLevel = ProofLevel.SIGNED_RESULT

    def verify(self) -> bool:
        raise NotImplementedError("signed result proof verification is not implemented")


@dataclass(frozen=True)
class ReproducibleProof:
    """Reserved type for future reproducibility verification."""

    proof_level: ProofLevel = ProofLevel.REPRODUCIBLE

    def verify(self) -> bool:
        raise NotImplementedError("reproducible proof verification is not implemented")


@dataclass(frozen=True)
class TEEAttestationProof:
    """Reserved type for future TEE attestation verification."""

    proof_level: ProofLevel = ProofLevel.TEE_ATTESTATION

    def verify(self) -> bool:
        raise NotImplementedError("TEE attestation verification is not implemented")


@dataclass(frozen=True)
class ZKProof:
    """Reserved type for future zero-knowledge proof verification."""

    proof_level: ProofLevel = ProofLevel.ZK_PROOF

    def verify(self) -> bool:
        raise NotImplementedError("ZK proof verification is not implemented")


@dataclass(frozen=True)
class Quote:
    provider: str
    capability: str
    resource_estimate: ResourceUnit
    settlement_price: SettlementCredit
    expires_at: float
    quote_id: str = field(default_factory=lambda: f"quote_{uuid4().hex}")

    def is_expired(self, now: float | None = None) -> bool:
        current = now if now is not None else datetime.now(timezone.utc).timestamp()
        return current > self.expires_at

    def to_json(self) -> dict[str, object]:
        return {
            "quote_id": self.quote_id,
            "provider": self.provider,
            "capability": self.capability,
            "resource_estimate": self.resource_estimate.to_json(),
            "settlement_price": self.settlement_price.to_json(),
            "expires_at": self.expires_at,
        }


@dataclass
class Transaction:
    sender: str
    receiver: str
    amount: SettlementCredit
    capability: str
    quote_id: str | None = None
    fee: SettlementCredit = field(default_factory=lambda: SettlementCredit(0))
    authorized_agent: str | None = None
    transaction_id: str = field(default_factory=lambda: f"tx_{uuid4().hex}")
    state: TransactionState = TransactionState.QUOTE_ACCEPTED
    settled_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.sender == self.receiver:
            raise ProtocolError("sender and receiver must differ")
        if self.fee.currency != self.amount.currency:
            raise ProtocolError("fee currency must match transaction amount currency")

    def transition(self, next_state: TransactionState) -> None:
        if next_state not in ALLOWED_TRANSITIONS[self.state]:
            raise ProtocolError(f"invalid transition: {self.state.value} -> {next_state.value}")
        self.state = next_state

    def to_json(self) -> dict[str, object]:
        return {
            "transaction_id": self.transaction_id,
            "quote_id": self.quote_id,
            "sender": self.sender,
            "receiver": self.receiver,
            "amount": self.amount.to_json(),
            "fee": self.fee.to_json(),
            "authorized_agent": self.authorized_agent,
            "capability": self.capability,
            "state": self.state.value,
            "settled_at": self.settled_at.isoformat() if self.settled_at else None,
        }


@dataclass(frozen=True)
class TaskResult:
    transaction_id: str
    output: object
    resource_usage: list[ResourceUnit]
    settlement_amount: SettlementCredit
    proof: MockProof

    def to_json(self) -> dict[str, object]:
        return {
            "transaction_id": self.transaction_id,
            "output": self.output,
            "resource_usage": [item.to_json() for item in self.resource_usage],
            "settlement_amount": self.settlement_amount.to_json(),
            "proof": self.proof.to_json(),
        }


class Ledger:
    def __init__(self) -> None:
        self.balances: dict[str, int] = {}
        self.fee_pool: int = 0
        self.total_supply: int = 0
        self.transactions: list[Transaction] = []

    def open_account(self, account: str, balance: SettlementCredit) -> None:
        if account in self.balances:
            raise ProtocolError(f"account already exists: {account}")
        self.balances[account] = balance.amount
        self.total_supply += balance.amount

    def balance_of(self, account: str) -> int:
        return self.balances.get(account, 0)

    def settle(self, transaction: Transaction) -> None:
        total_debit = transaction.amount.amount + transaction.fee.amount
        if self.balance_of(transaction.sender) < total_debit:
            raise ProtocolError("insufficient credit")
        before = self.snapshot()
        self.balances[transaction.sender] = self.balance_of(transaction.sender) - total_debit
        self.balances[transaction.receiver] = self.balance_of(transaction.receiver) + transaction.amount.amount
        self.fee_pool += transaction.fee.amount
        transaction.state = TransactionState.SETTLED
        transaction.settled_at = datetime.now(timezone.utc)
        self.transactions.append(transaction)
        if not self.verify_zero_sum(before):
            raise ProtocolError("ledger invariant failed")

    def refund(self, transaction: Transaction) -> None:
        transaction.transition(TransactionState.REFUNDED)

    def dispute(self, transaction: Transaction) -> None:
        transaction.transition(TransactionState.DISPUTED)

    def get_daily_spend(self, agent: str, owner: str, day: date) -> SettlementCredit:
        total = 0
        for transaction in self.transactions:
            if transaction.settled_at is None:
                continue
            if transaction.settled_at.date() != day:
                continue
            if transaction.sender != owner:
                continue
            if transaction.authorized_agent != agent:
                continue
            total += transaction.amount.amount + transaction.fee.amount
        return SettlementCredit(total)

    def snapshot(self) -> dict[str, object]:
        return {"balances": dict(self.balances), "fee_pool": self.fee_pool, "total_supply": self.total_supply}

    def verify_zero_sum(self, before: dict[str, object] | None = None) -> bool:
        if before is None:
            total = sum(self.balances.values()) + self.fee_pool
            return total == self.total_supply

        previous_balances = before["balances"]
        if not isinstance(previous_balances, dict):
            raise ProtocolError("invalid ledger snapshot")
        previous_fee_pool = before["fee_pool"]
        if not isinstance(previous_fee_pool, int):
            raise ProtocolError("invalid fee pool snapshot")

        before_total = sum(previous_balances.values()) + previous_fee_pool
        after_total = sum(self.balances.values()) + self.fee_pool
        return before_total == after_total

    def verify_transaction_zero_sum(self, before: dict[str, object], transaction: Transaction) -> bool:
        previous_balances = before["balances"]
        previous_fee_pool = before["fee_pool"]
        if not isinstance(previous_balances, dict) or not isinstance(previous_fee_pool, int):
            raise ProtocolError("invalid ledger snapshot")

        deltas: dict[str, int] = {}
        accounts: Iterable[str] = set(previous_balances) | set(self.balances)
        for account in accounts:
            deltas[account] = self.balance_of(account) - int(previous_balances.get(account, 0))

        return (
            deltas.get(transaction.sender) == -(transaction.amount.amount + transaction.fee.amount)
            and deltas.get(transaction.receiver) == transaction.amount.amount
            and self.fee_pool - previous_fee_pool == transaction.fee.amount
            and sum(deltas.values()) + (self.fee_pool - previous_fee_pool) == 0
        )
