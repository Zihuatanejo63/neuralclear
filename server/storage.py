from __future__ import annotations

import json
from pathlib import Path

from neuralclear import SettlementCredit, Transaction, TransactionState
from neuralclear.core import ProtocolError

from . import db


class SQLiteStorage:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.connection = db.connect(self.path)

    def save_agent(self, manifest: dict[str, object]) -> None:
        agent_id = str(manifest["agent_id"])
        self._upsert_json("agents", "agent_id", agent_id, manifest)

    def load_agents(self) -> list[dict[str, object]]:
        return self._load_json_table("agents")

    def save_quote(self, quote: dict[str, object]) -> None:
        self._upsert_json("quotes", "quote_id", str(quote["quote_id"]), quote)

    def save_task(self, task: dict[str, object]) -> None:
        self._upsert_json("tasks", "task_id", str(task["task_id"]), task)

    def load_tasks(self) -> list[dict[str, object]]:
        return self._load_json_table("tasks")

    def save_transaction(self, transaction: Transaction) -> None:
        self._upsert_json(
            "transactions",
            "transaction_id",
            transaction.transaction_id,
            transaction.to_json(),
        )

    def load_transactions(self) -> list[Transaction]:
        return [self._transaction_from_json(item) for item in self._load_json_table("transactions")]

    def save_receipt(self, receipt: dict[str, object]) -> None:
        self._upsert_json("receipts", "receipt_id", str(receipt["receipt_id"]), receipt)

    def load_receipts(self) -> list[dict[str, object]]:
        return self._load_json_table("receipts")

    def save_dispute(self, dispute: dict[str, object]) -> None:
        self._upsert_json("disputes", "dispute_id", str(dispute["dispute_id"]), dispute)

    def load_disputes(self) -> list[dict[str, object]]:
        return self._load_json_table("disputes")

    def save_balances(self, balances: dict[str, int], fee_pool: int, total_supply: int) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM balances")
            self.connection.executemany(
                "INSERT INTO balances(account, amount) VALUES (?, ?)",
                [(account, amount) for account, amount in balances.items()],
            )
            self.connection.execute(
                "INSERT INTO metadata(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                ("fee_pool", str(fee_pool)),
            )
            self.connection.execute(
                "INSERT INTO metadata(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                ("total_supply", str(total_supply)),
            )

    def load_balances(self) -> tuple[dict[str, int], int, int] | None:
        rows = self.connection.execute("SELECT account, amount FROM balances").fetchall()
        if not rows:
            return None
        metadata = {
            row["key"]: row["value"]
            for row in self.connection.execute("SELECT key, value FROM metadata").fetchall()
        }
        balances = {row["account"]: int(row["amount"]) for row in rows}
        return balances, int(metadata.get("fee_pool", 0)), int(metadata.get("total_supply", 0))

    def close(self) -> None:
        self.connection.close()

    def _upsert_json(self, table: str, key: str, value: str, payload: dict[str, object]) -> None:
        with self.connection:
            self.connection.execute(
                f"INSERT INTO {table}({key}, payload) VALUES (?, ?) "
                f"ON CONFLICT({key}) DO UPDATE SET payload=excluded.payload",
                (value, json.dumps(payload, sort_keys=True)),
            )

    def _load_json_table(self, table: str) -> list[dict[str, object]]:
        rows = self.connection.execute(f"SELECT payload FROM {table}").fetchall()
        return [json.loads(row["payload"]) for row in rows]

    @staticmethod
    def _transaction_from_json(payload: dict[str, object]) -> Transaction:
        amount = payload["amount"]
        fee = payload["fee"]
        if not isinstance(amount, dict) or not isinstance(fee, dict):
            raise ProtocolError("invalid stored transaction amount")
        transaction = Transaction(
            sender=str(payload["sender"]),
            receiver=str(payload["receiver"]),
            amount=SettlementCredit(**amount),
            fee=SettlementCredit(**fee),
            capability=str(payload["capability"]),
            quote_id=str(payload["quote_id"]) if payload.get("quote_id") else None,
            authorized_agent=str(payload["authorized_agent"])
            if payload.get("authorized_agent")
            else None,
            transaction_id=str(payload["transaction_id"]),
            state=TransactionState(str(payload["state"])),
        )
        settled_at = payload.get("settled_at")
        if isinstance(settled_at, str) and settled_at:
            from datetime import datetime

            transaction.settled_at = datetime.fromisoformat(settled_at)
        return transaction
