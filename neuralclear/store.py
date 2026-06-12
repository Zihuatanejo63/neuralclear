"""SQLite persistence: the clearing state survives restarts.

Snapshot-style store for `ClearingService`: balances, escrow, fee pool,
receipts, and disputes round-trip through a single SQLite file. Stdlib only.

    store = ClearingStore("clearing.db")
    store.save(service)            # after each settlement / resolution
    service2 = store.load()        # fresh process, same money
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .clearing import ClearingService, EscrowLedger

_SCHEMA = """
CREATE TABLE IF NOT EXISTS balances (account TEXT PRIMARY KEY, amount INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS escrow (transaction_id TEXT PRIMARY KEY, amount INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS receipts (receipt_id TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS disputes (dispute_id TEXT PRIMARY KEY, body TEXT NOT NULL);
"""


class ClearingStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.executescript(_SCHEMA)
        return conn

    # -- save ----------------------------------------------------------------
    def save(self, service: ClearingService) -> None:
        ledger = service.ledger
        with self._connect() as conn:
            conn.execute("DELETE FROM balances")
            conn.executemany(
                "INSERT INTO balances(account, amount) VALUES (?, ?)",
                list(ledger.balances.items()),
            )
            conn.execute("DELETE FROM escrow")
            if isinstance(ledger, EscrowLedger):
                conn.executemany(
                    "INSERT INTO escrow(transaction_id, amount) VALUES (?, ?)",
                    list(ledger.escrow.items()),
                )
            conn.execute("DELETE FROM meta")
            conn.executemany(
                "INSERT INTO meta(key, value) VALUES (?, ?)",
                [
                    ("fee_pool", str(ledger.fee_pool)),
                    ("total_supply", str(ledger.total_supply)),
                ],
            )
            conn.execute("DELETE FROM receipts")
            conn.executemany(
                "INSERT INTO receipts(receipt_id, body) VALUES (?, ?)",
                [(rid, json.dumps(body, default=str)) for rid, body in service.receipts.items()],
            )
            conn.execute("DELETE FROM disputes")
            conn.executemany(
                "INSERT INTO disputes(dispute_id, body) VALUES (?, ?)",
                [(did, json.dumps(d.to_json())) for did, d in service.disputes.items()],
            )

    # -- load ----------------------------------------------------------------
    def load(self, service: ClearingService | None = None) -> ClearingService:
        service = service or ClearingService(ledger=EscrowLedger())
        ledger = service.ledger
        with self._connect() as conn:
            ledger.balances = {
                account: amount
                for account, amount in conn.execute("SELECT account, amount FROM balances")
            }
            if isinstance(ledger, EscrowLedger):
                ledger.escrow = {
                    tx_id: amount
                    for tx_id, amount in conn.execute("SELECT transaction_id, amount FROM escrow")
                }
            meta = dict(conn.execute("SELECT key, value FROM meta"))
            ledger.fee_pool = int(meta.get("fee_pool", "0"))
            ledger.total_supply = int(meta.get("total_supply", "0"))
            service.receipts = {
                rid: json.loads(body)
                for rid, body in conn.execute("SELECT receipt_id, body FROM receipts")
            }
        return service
