from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Receipt:
    receipt_id: str
    transaction_id: str
    quote_id: str
    buyer: str
    provider: str
    amount: int
    fee: int
    currency: str
    timestamp: str
    result_hash: str
    signature: str
    state: str
    created_at: str
    sender: str | None = None
    receiver: str | None = None

    def to_json(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class StoredTask:
    task_id: str
    quote_id: str
    state: str
    result: dict[str, object] | None = None

    def to_json(self) -> dict[str, object]:
        return asdict(self)
