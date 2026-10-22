from concurrent.futures import ProcessPoolExecutor
import json
import multiprocessing
from pathlib import Path
import tempfile
import unittest

from neuralclear.core import ProtocolError
from neuralclear.escrow import EscrowLedger
from neuralclear.journal import FileCheckpoint
from tests.test_signed_mandates import KEYS, mandate


def writer(args):
    path, cp, index = args
    ledger = EscrowLedger(
        journal_path=path,
        checkpoint=FileCheckpoint(cp),
        mandate_keys=KEYS,
        clock=lambda: 100,
        wait_for_writer=True,
    )
    try:
        tx = str(index)
        ledger.create(tx, "buyer", "provider", 50, 5)
        ledger.authorize(tx, "m1", "delegate", "summarize")
        try:
            ledger.transition(tx, "QUOTE_ACCEPTED")
            return True
        except ProtocolError:
            return False
    finally:
        ledger.close()


class MultiprocessJournalTests(unittest.TestCase):
    def test_serialized_writers_preserve_chain_and_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, cp = str(Path(tmp) / "events"), str(Path(tmp) / "head")
            ledger = EscrowLedger(
                journal_path=path,
                checkpoint=FileCheckpoint(cp, initialize=True),
                mandate_keys=KEYS,
                clock=lambda: 100,
            )
            ledger.open_account("buyer", 1000)
            ledger.open_account("provider")
            ledger.register_mandate(mandate())
            ledger.close()
            with ProcessPoolExecutor(
                max_workers=4, mp_context=multiprocessing.get_context("spawn")
            ) as pool:
                results = list(pool.map(writer, [(path, cp, i) for i in range(8)]))
            self.assertEqual(sum(results), 1)
            restored = EscrowLedger(
                journal_path=path, checkpoint=FileCheckpoint(cp), mandate_keys=KEYS
            )
            try:
                self.assertEqual(restored.mandate_usage("m1")["reserved"], 55)
                for i in range(8):
                    self.assertEqual(restored.get(str(i))["transaction_id"], str(i))
                events = [json.loads(line) for line in Path(path).read_text().splitlines()]
                self.assertEqual(len(events), 20)  # setup 3 + 8*(create+authorize) + accept
                self.assertEqual([e["seq"] for e in events], list(range(20)))
                self.assertEqual(len({e["hash"] for e in events}), 20)
            finally:
                restored.close()
