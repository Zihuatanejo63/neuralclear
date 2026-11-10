from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from neuralclear.core import ProtocolError
from neuralclear.escrow import EscrowLedger
from neuralclear.wire import ZERO_HASH
from neuralclear.journal import FileCheckpoint


class Checkpoint:
    """Test-only trusted store, deliberately separate from the log file."""

    def __init__(self):
        self.value = {"count": 0, "hash": ZERO_HASH}

    def read(self):
        return deepcopy(self.value)

    def compare_and_set(self, old, new):
        if self.value != old:
            raise ProtocolError("checkpoint conflict")
        self.value = deepcopy(new)


class JournalTests(unittest.TestCase):
    def test_file_checkpoint_survives_recreation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, anchor = Path(tmp) / "log", Path(tmp) / "trusted"
            ledger = self.prepare(path, FileCheckpoint(anchor, initialize=True))
            expected = ledger.snapshot()
            ledger.close()
            restored = EscrowLedger(journal_path=path, checkpoint=FileCheckpoint(anchor))
            self.assertEqual(restored.snapshot(), expected)
            restored.close()

    def prepare(self, path, checkpoint):
        ledger = EscrowLedger(journal_path=path, checkpoint=checkpoint)
        ledger.open_account("buyer", 100)
        ledger.open_account("provider")
        ledger.create("tx", "buyer", "provider", 50, 5)
        for state in ("QUOTE_ACCEPTED", "TASK_SUBMITTED", "TASK_RUNNING"):
            ledger.transition("tx", state)
        ledger.meter("tx", 30, "a" * 64)
        ledger.transition("tx", "DISPUTED")
        ledger.transition("tx", "SETTLED", amount=20, fee=2)
        return ledger

    def test_reload_state_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, cp = Path(tmp) / "ledger.jsonl", Checkpoint()
            ledger = self.prepare(path, cp)
            expected = ledger.snapshot(), ledger.get("tx"), ledger.chain("tx")
            ledger.close()
            restored = EscrowLedger(journal_path=path, checkpoint=cp)
            self.assertEqual(
                expected, (restored.snapshot(), restored.get("tx"), restored.chain("tx"))
            )
            restored.open_account("next")
            restored.close()

    def test_truncation_always_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, cp = Path(tmp) / "ledger.jsonl", Checkpoint()
            self.prepare(path, cp).close()
            lines = path.read_bytes().splitlines(keepends=True)
            for length in range(len(lines)):
                with self.subTest(length=length):
                    path.write_bytes(b"".join(lines[:length]))
                    with self.assertRaises(ProtocolError):
                        EscrowLedger(journal_path=path, checkpoint=cp)

    def test_each_event_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, cp = Path(tmp) / "ledger.jsonl", Checkpoint()
            self.prepare(path, cp).close()
            lines = path.read_text().splitlines()
            for index in range(len(lines)):
                with self.subTest(index=index):
                    altered = lines.copy()
                    event = json.loads(altered[index])
                    event["method"] = "open_account"
                    event["args"] = ["attacker", 9000]
                    altered[index] = json.dumps(event)
                    path.write_text("\n".join(altered) + "\n")
                    with self.assertRaises(ProtocolError):
                        EscrowLedger(journal_path=path, checkpoint=cp)

    def test_failed_mutation_not_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, cp = Path(tmp) / "ledger.jsonl", Checkpoint()
            ledger = self.prepare(path, cp)
            before = path.read_bytes()
            with self.assertRaises(ProtocolError):
                ledger.transition("tx", "TASK_RUNNING")
            self.assertEqual(before, path.read_bytes())
            ledger.close()

    def test_checkpoint_failure_poison_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, cp = Path(tmp) / "ledger.jsonl", Checkpoint()
            ledger = EscrowLedger(journal_path=path, checkpoint=cp)
            cp.compare_and_set = lambda old, new: None
            with self.assertRaises(ProtocolError):
                ledger.open_account("buyer", 100)
            self.assertEqual(ledger.snapshot()["balances"], {})
            with self.assertRaises(ProtocolError):
                ledger.open_account("provider")
            ledger.close()
            with self.assertRaises(ProtocolError):
                EscrowLedger(journal_path=path, checkpoint=cp)
