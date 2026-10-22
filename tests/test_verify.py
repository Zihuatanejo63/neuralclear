from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from neuralclear.core import ProtocolError
from neuralclear.verify import verify
from neuralclear.wire import authenticate, canonical, load_json
from tests.test_escrow import ledger_at

KEY = b"conformance-only-key"


def evidence():
    ledger = ledger_at("SETTLED")
    return ledger.receipt("tx", key=KEY, key_id="test"), ledger.chain("tx")


class VerifyTests(unittest.TestCase):
    def test_verify_without_ledger(self):
        receipt, chain = evidence()
        self.assertTrue(verify(receipt, chain, {"test": KEY}))

    def test_every_receipt_field_is_authenticated(self):
        receipt, chain = evidence()
        for name in receipt:
            with self.subTest(field=name):
                tampered = deepcopy(receipt)
                value = tampered[name]
                tampered[name] = value + 1 if type(value) is int else "tampered"
                with self.assertRaises(ProtocolError):
                    verify(tampered, chain, {"test": KEY})

    def test_every_meter_field_is_bound(self):
        receipt, chain = evidence()
        for name in chain[0]:
            with self.subTest(field=name):
                tampered = deepcopy(chain)
                value = tampered[0][name]
                tampered[0][name] = value + 1 if type(value) is int else "tampered"
                with self.assertRaises(ProtocolError):
                    verify(receipt, tampered, {"test": KEY})

    def test_truncation_reordering_and_splicing_rejected(self):
        ledger = ledger_at("TASK_RUNNING")
        ledger.meter("tx", 0, "b" * 64)
        for state in ["RESULT_DELIVERED", "PROOF_VERIFIED", "SETTLED"]:
            ledger.transition("tx", state, **({"amount": 50} if state == "SETTLED" else {}))
        receipt, chain = ledger.receipt("tx", key=KEY, key_id="test"), ledger.chain("tx")
        self.assertTrue(verify(receipt, chain, {"test": KEY}))
        for bad in [chain[:-1], chain[::-1], chain + chain[:1], [chain[1], chain[1]]]:
            with self.assertRaises(ProtocolError):
                verify(receipt, bad, {"test": KEY})

    def test_signed_but_invalid_semantics_rejected(self):
        receipt, chain = evidence()
        for change in [
            {"amount": 51},
            {"refund": 1},
            {"fee": 6},
            {"deltas": {"buyer": -54, "provider": 49, "fee_pool": 5, "escrow": 0}},
            {"history": ["QUOTE_REQUESTED", "SETTLED"], "revision": 1},
            {"rate": 2},
            {"funded": 1},
            {"buyer": "provider"},
        ]:
            with self.subTest(change=change):
                bad = dict(receipt, **change)
                bad["signature"] = authenticate(
                    {k: v for k, v in bad.items() if k != "signature"}, KEY
                )
                with self.assertRaises(ProtocolError):
                    verify(bad, chain, {"test": KEY})

    def test_key_algorithm_and_json_rejection(self):
        receipt, chain = evidence()
        for keys in [{}, {"test": b"wrong"}]:
            with self.assertRaises(ProtocolError):
                verify(receipt, chain, keys)
        bad = dict(receipt, algorithm="NONE")
        with self.assertRaises(ProtocolError):
            verify(bad, chain, {"test": KEY})
        for text in ['{"a":1,"a":2}', '{"a":NaN}', '{"a":1.5}', '{"a":9007199254740992}']:
            with self.assertRaises(ProtocolError):
                load_json(text)
        self.assertEqual(canonical({"z": 1, "a": 'quote"\\'}), b'{"a":"quote\\"\\\\","z":1}')

    def test_refund_slash_expiration_receipts(self):
        for state in ["REFUNDED", "SLASHED", "EXPIRED"]:
            with self.subTest(state=state):
                ledger = ledger_at(state)
                self.assertTrue(
                    verify(
                        ledger.receipt("tx", key=KEY, key_id="test"),
                        ledger.chain("tx"),
                        {"test": KEY},
                    )
                )

    def test_cli_exit_codes(self):
        receipt, chain = evidence()
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "receipt.json").write_text(json.dumps(receipt))
            (directory / "chain.json").write_text(json.dumps(chain))
            (directory / "key").write_bytes(KEY)
            command = [
                sys.executable,
                "-m",
                "neuralclear.verify",
                str(directory / "receipt.json"),
                str(directory / "chain.json"),
                "--key-id",
                "test",
                "--key-file",
                str(directory / "key"),
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual((result.returncode, result.stdout.strip()), (0, "VALID"))
            (directory / "chain.json").write_text("[]")
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("INVALID", result.stdout)

    def test_meter_budget_and_frozen_state(self):
        ledger = ledger_at("TASK_RUNNING")
        before = ledger.chain("tx")
        with self.assertRaises(ProtocolError):
            ledger.meter("tx", 1, "a" * 64)
        ledger.transition("tx", "DISPUTED")
        with self.assertRaises(ProtocolError):
            ledger.meter("tx", 0, "a" * 64)
        self.assertEqual(ledger.chain("tx"), before)
