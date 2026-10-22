import hashlib
import hmac
import json
from pathlib import Path
import unittest

from neuralclear.core import ProtocolError
from neuralclear.escrow import EscrowLedger
from neuralclear.verify import verify


class ProtocolVectorTests(unittest.TestCase):
    def test_frozen_vectors(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/escrow_v1.json").read_text())
        key = bytes.fromhex(fixture["key_hex"])
        for case in fixture["cases"]:
            with self.subTest(case=case["name"]):
                expected = case["expected"]
                if not expected["valid"]:
                    with self.assertRaises(ProtocolError):
                        verify(expected["receipt"], expected["chain"], {"test": key})
                    continue
                setup = case["input"]
                ledger = EscrowLedger(setup["currency"])
                for account, amount in setup["balances"].items():
                    ledger.open_account(account, amount)
                ledger.create(**setup["terms"])
                transaction_id = setup["terms"]["transaction_id"]
                for operation in setup["operations"]:
                    if "meter" in operation:
                        ledger.meter(transaction_id, **operation["meter"])
                    else:
                        ledger.transition(transaction_id, **operation)
                self.assertEqual(ledger.snapshot(), expected["snapshot"])
                self.assertEqual(ledger.chain(transaction_id), expected["chain"])
                self.assertEqual(
                    ledger.receipt(transaction_id, key=key, key_id="test"), expected["receipt"]
                )
                self.assertTrue(verify(expected["receipt"], expected["chain"], {"test": key}))
                # Independent primitive calculation from the SPEC, without wire helpers.
                for event in expected["chain"]:
                    body = {k: v for k, v in event.items() if k != "hash"}
                    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode(
                        "ascii"
                    )
                    self.assertEqual(
                        hashlib.sha256(b"NeuralClear/meter/v1\n" + encoded).hexdigest(),
                        event["hash"],
                    )
                receipt = expected["receipt"]
                body = {k: v for k, v in receipt.items() if k != "signature"}
                encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("ascii")
                self.assertEqual(
                    hmac.new(
                        key, b"NeuralClear/receipt/v1\n" + encoded, hashlib.sha256
                    ).hexdigest(),
                    receipt["signature"],
                )
