"""Durable replay protection for signed protocol messages.

A signed message is accepted once. The seen-nonce row is stored in SQLite so a
process restart does not forget it. Timestamp must fall inside the configured
clock skew, and the message must still be inside its TTL.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .core import ProtocolError


class ReplayStore:
    def __init__(self, path: str | Path, *, skew_seconds: int = 120, ttl_seconds: int = 600) -> None:
        if skew_seconds < 0 or ttl_seconds <= 0:
            raise ProtocolError("invalid replay window")
        self.skew_seconds = skew_seconds
        self.ttl_seconds = ttl_seconds
        self.path = str(path)
        self._db = sqlite3.connect(self.path)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS seen_nonces ("
            "nonce TEXT PRIMARY KEY, message_id TEXT NOT NULL, expires_at INTEGER NOT NULL)"
        )
        self._db.commit()

    def admit(self, *, message_id: str, nonce: object, timestamp: object, now: int) -> None:
        if not isinstance(message_id, str) or not message_id:
            raise ProtocolError("message id required")
        if not isinstance(nonce, str) or not nonce:
            raise ProtocolError("nonce required")
        if type(timestamp) is not int or type(now) is not int:
            raise ProtocolError("trusted timestamp required")
        age = now - timestamp
        if timestamp > now + self.skew_seconds or age > self.skew_seconds:
            raise ProtocolError("timestamp outside clock skew")
        if age > self.ttl_seconds:
            raise ProtocolError("signed message expired")
        self._db.execute("DELETE FROM seen_nonces WHERE expires_at <= ?", (now,))
        try:
            self._db.execute(
                "INSERT INTO seen_nonces (nonce, message_id, expires_at) VALUES (?, ?, ?)",
                (nonce, message_id, now + self.ttl_seconds),
            )
        except sqlite3.IntegrityError as exc:
            raise ProtocolError("replayed nonce") from exc
        else:
            self._db.commit()

    def close(self) -> None:
        self._db.close()


def accept_signed_message(body: dict, store: ReplayStore, *, message_id: str, now: int) -> None:
    """Check nonce, timestamp, skew, and TTL, then remember the nonce."""
    store.admit(
        message_id=message_id,
        nonce=body.get("nonce"),
        timestamp=body.get("timestamp") if type(body.get("timestamp")) is int else body.get("signed_at"),
        now=now,
    )
