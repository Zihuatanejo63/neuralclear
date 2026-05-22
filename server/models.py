from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Receipt:
    receipt_id: str
    transaction_id: str
    quote_id: str
    sender: str
    receiver: str
    amount: dict[str, int | str]
    fee: dict[str, int | str]
    state: str
    created_at: str

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
