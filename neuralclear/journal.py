"""Append-only single-writer journal with an independently trusted checkpoint.

The checkpoint object must implement read() and compare_and_set(old, new).
Production callers must back it with durable, rollback-protected storage outside
the journal's trust boundary. A mismatch fails closed, including crash windows;
recovery requires operator reconciliation, never silently accepting a shorter log.
"""

from copy import deepcopy
from functools import wraps
import hashlib
import os
from pathlib import Path
import tempfile

from .core import ProtocolError
from .wire import canonical, load_json, ZERO_HASH


class FileCheckpoint:
    """Durable checkpoint on a separately protected filesystem, NOT self-trusting.

    The operator must prevent rollback/deletion of this file independently of the
    journal. initialize=True is only for a brand-new ledger, never auto-recovery.
    """

    def __init__(self, path, *, initialize=False):
        self.path = Path(path)
        if initialize:
            with self.path.open("xb") as stream:
                stream.write(canonical({"count": 0, "hash": ZERO_HASH}))
                stream.flush()
                os.fsync(stream.fileno())
            self._sync_directory()

    def _sync_directory(self):
        fd = os.open(str(self.path.parent), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def read(self):
        return load_json(self.path.read_text(encoding="ascii"))

    def compare_and_set(self, old, new):
        import fcntl

        with open(str(self.path) + ".lock", "a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if self.read() != old:
                raise ProtocolError("checkpoint conflict")
            name = None
            try:
                with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as stream:
                    name = stream.name
                    stream.write(canonical(new))
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, self.path)
                self._sync_directory()
            finally:
                if name is not None and os.path.exists(name):
                    os.unlink(name)


def event_hash(body):
    return hashlib.sha256(b"NeuralClear/journal/v1\n" + canonical(body)).hexdigest()


def mutation(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            if self._broken:
                raise ProtocolError("journal unavailable; reconcile and reopen")
            if self._in_mutation:
                return method(self, *args, **kwargs)
            before = {name: deepcopy(getattr(self, name)) for name in self._state_fields}
            self._in_mutation = True
            self._event_time = (
                self._replay_time if self._replay_time is not None else int(self._clock())
            )
            try:
                result = method(self, *args, **kwargs)
                if self._journal is not None:
                    self._journal.append(method.__name__, list(args), kwargs, self._event_time)
                return result
            except Exception:
                for name, value in before.items():
                    setattr(self, name, value)
                if self._journal is not None and self._journal.failed:
                    self._broken = True
                raise
            finally:
                self._in_mutation = False

    wrapped.journal_mutation = True
    return wrapped


class Journal:
    def __init__(self, path, checkpoint, currency, replay, *, wait=False):
        import fcntl

        self.file = open(path, "a+b")
        self.checkpoint = checkpoint
        self.currency = currency
        self.head = {"count": 0, "hash": ZERO_HASH}
        self.failed = False
        try:
            # Hold through recovery, budget checks, appends and close. Waiting
            # writers replay the latest state, never append from stale balances.
            fcntl.flock(self.file, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
            self.file.seek(0)
            events = []
            for line in self.file:
                if not line.endswith(b"\n"):
                    raise ProtocolError("incomplete journal event")
                event = load_json(line.decode("ascii"))
                if set(event) != {
                    "seq",
                    "previous",
                    "currency",
                    "method",
                    "args",
                    "kwargs",
                    "hash",
                    "at",
                }:
                    raise ProtocolError("invalid journal event")
                body = {k: v for k, v in event.items() if k != "hash"}
                if (
                    event["seq"] != self.head["count"]
                    or event["previous"] != self.head["hash"]
                    or event["currency"] != currency
                    or event_hash(body) != event["hash"]
                ):
                    raise ProtocolError("journal hash chain mismatch")
                self.head = {"count": self.head["count"] + 1, "hash": event["hash"]}
                events.append(event)
            if checkpoint.read() != self.head:
                raise ProtocolError("trusted checkpoint mismatch (truncation or rollback)")
            for event in events:
                replay(event)
        except (ValueError, TypeError, KeyError) as exc:
            self.file.close()
            raise ProtocolError("invalid journal") from exc
        except Exception:
            self.file.close()
            raise

    def append(self, method, args, kwargs, at):
        body = dict(
            seq=self.head["count"],
            previous=self.head["hash"],
            currency=self.currency,
            method=method,
            args=args,
            kwargs=kwargs,
            at=at,
        )
        hashed = event_hash(body)
        data = canonical(dict(body, hash=hashed)) + b"\n"
        new_head = {"count": self.head["count"] + 1, "hash": hashed}
        try:
            if self.checkpoint.read() != self.head:
                raise ProtocolError("checkpoint changed outside writer")
            self.file.write(data)
            self.file.flush()
            os.fsync(self.file.fileno())
            self.checkpoint.compare_and_set(dict(self.head), dict(new_head))
            if self.checkpoint.read() != new_head:
                raise ProtocolError("checkpoint update failed")
            self.head = new_head
        except Exception:
            self.failed = True
            raise

    def close(self):
        self.file.close()
