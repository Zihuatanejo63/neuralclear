"""SQLite directory of tenants and their protocol-credit clearing snapshots.

API keys are stored only as hashes. This store never accepts or returns a raw key.
Clearing balances here are protocol credits, not customer funds.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usage_months (
    tenant_id TEXT NOT NULL,
    month TEXT NOT NULL,
    settlements INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, month)
);
CREATE TABLE IF NOT EXISTS balances (
    tenant_id TEXT NOT NULL,
    account TEXT NOT NULL,
    amount INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, account)
);
CREATE TABLE IF NOT EXISTS escrow (
    tenant_id TEXT NOT NULL,
    transaction_id TEXT NOT NULL,
    amount INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, transaction_id)
);
CREATE TABLE IF NOT EXISTS ledger_meta (
    tenant_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (tenant_id, key)
);
CREATE TABLE IF NOT EXISTS receipts (
    tenant_id TEXT NOT NULL,
    receipt_id TEXT NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (tenant_id, receipt_id)
);
CREATE TABLE IF NOT EXISTS disputes (
    tenant_id TEXT NOT NULL,
    dispute_id TEXT NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (tenant_id, dispute_id)
);
CREATE TABLE IF NOT EXISTS transactions (
    tenant_id TEXT NOT NULL,
    transaction_id TEXT NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (tenant_id, transaction_id)
);
CREATE TABLE IF NOT EXISTS channels (
    tenant_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (tenant_id, channel_id)
);
"""


@dataclass
class TenantSnapshot:
    tenant_id: str
    name: str
    key_hash: str
    created_at: str
    usage: dict[str, int] = field(default_factory=dict)
    balances: dict[str, int] = field(default_factory=dict)
    escrow: dict[str, int] = field(default_factory=dict)
    fee_pool: int = 0
    total_supply: int = 0
    receipts: dict[str, dict[str, object]] = field(default_factory=dict)
    disputes: dict[str, dict[str, object]] = field(default_factory=dict)
    transactions: dict[str, dict[str, object]] = field(default_factory=dict)
    channels: dict[str, dict[str, object]] = field(default_factory=dict)


class TenantStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        parent = Path(self.path).parent
        if str(parent) not in {"", "."}:
            parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def ping(self) -> bool:
        try:
            with self._lock:
                self._conn.execute("SELECT 1")
            return True
        except sqlite3.Error:
            return False

    def list_ids(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT tenant_id FROM tenants ORDER BY tenant_id"
            ).fetchall()
        return [str(row["tenant_id"]) for row in rows]

    def tenant_id_for_hash(self, key_hash: str) -> str | None:
        if not key_hash:
            return None
        with self._lock:
            row = self._conn.execute(
                "SELECT tenant_id FROM tenants WHERE key_hash = ?",
                (key_hash,),
            ).fetchone()
        if row is None:
            return None
        return str(row["tenant_id"])

    def update_key_hash(self, tenant_id: str, key_hash: str) -> None:
        """Replace the stored hash. Ledger rows are left untouched."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = self._conn.execute(
                    "UPDATE tenants SET key_hash = ? WHERE tenant_id = ?",
                    (key_hash, tenant_id),
                )
                if cursor.rowcount != 1:
                    self._conn.rollback()
                    raise KeyError(tenant_id)
                self._conn.commit()
            except sqlite3.IntegrityError as exc:
                self._conn.rollback()
                raise ValueError("api key already in use") from exc
            except Exception:
                self._conn.rollback()
                raise

    def insert(self, snap: TenantSnapshot) -> None:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute(
                    """
                    INSERT INTO tenants(tenant_id, name, key_hash, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (snap.tenant_id, snap.name, snap.key_hash, snap.created_at),
                )
                self._write_state(snap)
                self._conn.commit()
            except sqlite3.IntegrityError as exc:
                self._conn.rollback()
                raise ValueError("api key already in use") from exc
            except Exception:
                self._conn.rollback()
                raise

    def save_state(self, snap: TenantSnapshot) -> None:
        """Persist clearing state without rewriting the API-key hash."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._write_state(snap)
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def load(self, tenant_id: str) -> TenantSnapshot | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT tenant_id, name, key_hash, created_at FROM tenants WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
            if row is None:
                return None
            snap = TenantSnapshot(
                tenant_id=str(row["tenant_id"]),
                name=str(row["name"]),
                key_hash=str(row["key_hash"]),
                created_at=str(row["created_at"]),
            )
            snap.usage = {
                str(month): int(count)
                for month, count in self._conn.execute(
                    "SELECT month, settlements FROM usage_months WHERE tenant_id = ?",
                    (tenant_id,),
                )
            }
            snap.balances = {
                str(account): int(amount)
                for account, amount in self._conn.execute(
                    "SELECT account, amount FROM balances WHERE tenant_id = ?",
                    (tenant_id,),
                )
            }
            snap.escrow = {
                str(tx_id): int(amount)
                for tx_id, amount in self._conn.execute(
                    "SELECT transaction_id, amount FROM escrow WHERE tenant_id = ?",
                    (tenant_id,),
                )
            }
            meta = {
                str(key): str(value)
                for key, value in self._conn.execute(
                    "SELECT key, value FROM ledger_meta WHERE tenant_id = ?",
                    (tenant_id,),
                )
            }
            snap.fee_pool = int(meta.get("fee_pool", "0"))
            snap.total_supply = int(meta.get("total_supply", "0"))
            snap.receipts = {
                str(rid): json.loads(body)
                for rid, body in self._conn.execute(
                    "SELECT receipt_id, body FROM receipts WHERE tenant_id = ?",
                    (tenant_id,),
                )
            }
            snap.disputes = {
                str(did): json.loads(body)
                for did, body in self._conn.execute(
                    "SELECT dispute_id, body FROM disputes WHERE tenant_id = ?",
                    (tenant_id,),
                )
            }
            snap.transactions = {
                str(tx_id): json.loads(body)
                for tx_id, body in self._conn.execute(
                    "SELECT transaction_id, body FROM transactions WHERE tenant_id = ?",
                    (tenant_id,),
                )
            }
            snap.channels = {
                str(channel_id): json.loads(body)
                for channel_id, body in self._conn.execute(
                    "SELECT channel_id, body FROM channels WHERE tenant_id = ?",
                    (tenant_id,),
                )
            }
            return snap

    def _write_state(self, snap: TenantSnapshot) -> None:
        tenant_id = snap.tenant_id
        self._conn.execute("DELETE FROM usage_months WHERE tenant_id = ?", (tenant_id,))
        self._conn.executemany(
            """
            INSERT INTO usage_months(tenant_id, month, settlements) VALUES (?, ?, ?)
            """,
            [(tenant_id, month, count) for month, count in snap.usage.items()],
        )
        self._conn.execute("DELETE FROM balances WHERE tenant_id = ?", (tenant_id,))
        self._conn.executemany(
            "INSERT INTO balances(tenant_id, account, amount) VALUES (?, ?, ?)",
            [(tenant_id, account, amount) for account, amount in snap.balances.items()],
        )
        self._conn.execute("DELETE FROM escrow WHERE tenant_id = ?", (tenant_id,))
        self._conn.executemany(
            "INSERT INTO escrow(tenant_id, transaction_id, amount) VALUES (?, ?, ?)",
            [(tenant_id, tx_id, amount) for tx_id, amount in snap.escrow.items()],
        )
        self._conn.execute("DELETE FROM ledger_meta WHERE tenant_id = ?", (tenant_id,))
        self._conn.executemany(
            "INSERT INTO ledger_meta(tenant_id, key, value) VALUES (?, ?, ?)",
            [
                (tenant_id, "fee_pool", str(snap.fee_pool)),
                (tenant_id, "total_supply", str(snap.total_supply)),
            ],
        )
        self._conn.execute("DELETE FROM receipts WHERE tenant_id = ?", (tenant_id,))
        self._conn.executemany(
            "INSERT INTO receipts(tenant_id, receipt_id, body) VALUES (?, ?, ?)",
            [
                (tenant_id, rid, json.dumps(body, default=str, sort_keys=True))
                for rid, body in snap.receipts.items()
            ],
        )
        self._conn.execute("DELETE FROM disputes WHERE tenant_id = ?", (tenant_id,))
        self._conn.executemany(
            "INSERT INTO disputes(tenant_id, dispute_id, body) VALUES (?, ?, ?)",
            [
                (tenant_id, did, json.dumps(body, default=str, sort_keys=True))
                for did, body in snap.disputes.items()
            ],
        )
        self._conn.execute("DELETE FROM transactions WHERE tenant_id = ?", (tenant_id,))
        self._conn.executemany(
            "INSERT INTO transactions(tenant_id, transaction_id, body) VALUES (?, ?, ?)",
            [
                (tenant_id, tx_id, json.dumps(body, default=str, sort_keys=True))
                for tx_id, body in snap.transactions.items()
            ],
        )
        self._conn.execute("DELETE FROM channels WHERE tenant_id = ?", (tenant_id,))
        self._conn.executemany(
            "INSERT INTO channels(tenant_id, channel_id, body) VALUES (?, ?, ?)",
            [
                (tenant_id, channel_id, json.dumps(body, default=str, sort_keys=True))
                for channel_id, body in snap.channels.items()
            ],
        )
