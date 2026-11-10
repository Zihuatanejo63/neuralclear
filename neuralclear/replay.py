"""Durable replay protection for signed protocol messages.

A signed message is accepted once. The seen-nonce row is stored in SQLite so a
process restart does not forget it. Timestamp must fall inside the configured
clock skew, and the message must still be inside its TTL.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .core import ProtocolError

_OPEN: dict[str, "ReplayStore"] = {}


class ReplayStore:
    def __init__(self, path: str | Path, *, skew_seconds: int = 30, ttl_seconds: int = 86_400) -> None:
        if skew_seconds < 0 or ttl_seconds <= 0:
            raise ProtocolError("invalid replay window")
        self.skew_seconds = skew_seconds
        self.ttl_seconds = ttl_seconds
        self.path = str(path)
        self._db = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS seen_nonces ("
            "nonce TEXT NOT NULL, phase TEXT NOT NULL, message_id TEXT NOT NULL, "
            "expires_at INTEGER NOT NULL, PRIMARY KEY (nonce, phase))"
        )

    def admit(
        self,
        *,
        message_id: str,
        nonce: object,
        timestamp: object,
        now: int,
        phase: str = "accept",
    ) -> None:
        if not isinstance(message_id, str) or not message_id:
            raise ProtocolError("message id required")
        if not isinstance(nonce, str) or not nonce:
            raise ProtocolError("nonce required")
        if not isinstance(phase, str) or not phase:
            raise ProtocolError("replay phase required")
        if type(timestamp) is not int or type(now) is not int:
            raise ProtocolError("trusted timestamp required")
        age = now - timestamp
        if timestamp > now + self.skew_seconds or age > self.skew_seconds:
            raise ProtocolError("timestamp outside clock skew")
        if age > self.ttl_seconds:
            raise ProtocolError("signed message expired")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            self._db.execute("DELETE FROM seen_nonces WHERE expires_at <= ?", (now,))
            self._db.execute(
                "INSERT INTO seen_nonces (nonce, phase, message_id, expires_at) VALUES (?, ?, ?, ?)",
                (nonce, phase, message_id, now + self.ttl_seconds),
            )
            self._db.commit()
        except sqlite3.IntegrityError:
            self._db.rollback()
            raise ProtocolError("replayed nonce") from None
        except Exception:
            self._db.rollback()
            raise

    def close(self) -> None:
        self._db.close()


def accept_signed_message(body: dict, store: ReplayStore, *, message_id: str, now: int) -> None:
    """Check nonce, timestamp, skew, and TTL, then remember the nonce."""
    timestamp = body.get("timestamp") if type(body.get("timestamp")) is int else body.get("signed_at")
    store.admit(message_id=message_id, nonce=body.get("nonce"), timestamp=timestamp, now=now)


def replay_store_path() -> str:
    return os.environ.get("NEURALCLEAR_REPLAY_STORE", "")


def open_replay_store() -> ReplayStore | None:
    """Open the configured store. Production with no path fails closed."""
    path = replay_store_path()
    mode = os.environ.get("NEURALCLEAR_MODE", "sandbox")
    if mode not in {"sandbox", "production"}:
        raise ProtocolError("unknown NEURALCLEAR_MODE")
    if not path:
        if mode == "production":
            raise ProtocolError("production requires NEURALCLEAR_REPLAY_STORE")
        return None
    current = _OPEN.get(path)
    if current is None:
        current = ReplayStore(path)
        _OPEN[path] = current
    return current


def record_replay(body: dict, phase: str, message_id: str, *, now: int | None = None) -> None:
    """Admit a signed message. No-op in sandbox when no store is configured."""
    store = open_replay_store()
    if store is None:
        return
    timestamp = body.get("signed_at") if type(body.get("signed_at")) is int else body.get("timestamp")
    if not isinstance(body.get("nonce"), str) or type(timestamp) is not int:
        if os.environ.get("NEURALCLEAR_MODE") == "production":
            raise ProtocolError("nonce and integer timestamp required")
        return
    store.admit(
        message_id=message_id,
        nonce=body["nonce"],
        timestamp=timestamp,
        now=int(time_now() if now is None else now),
        phase=phase,
    )


def time_now() -> int:
    import time

    return int(time.time())
