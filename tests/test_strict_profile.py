import copy
import hashlib
import unittest
import tempfile
from pathlib import Path

from neuralclear.core import ProtocolError, MockProof
from neuralclear.ed25519 import public_key
from neuralclear.strict_escrow import StrictEscrowLedger
from neuralclear.wire import canonical, sign
from neuralclear.merkle import inclusion
from neuralclear.verify import verify_meter_inclusion
from neuralclear.journal import FileCheckpoint

SEEDS = {k: bytes([i]) * 32 for i, k in enumerate(("a", "b", "p"), 1)}
KEYS = {k: ("Ed25519", public_key(v)) for k, v in SEEDS.items()}


def running(**kwargs):
    ledger = StrictEscrowLedger(
        arbitrator_keys={k: KEYS[k] for k in ("a", "b")},
        provider_keys={"provider": {"p": KEYS["p"]}},
        quorum=2,
        **kwargs,
    )
    ledger.open_account("buyer", 100)
    ledger.open_account("provider")
    ledger.create("tx", "buyer", "provider", 100)
    for state in ("QUOTE_ACCEPTED", "TASK_SUBMITTED", "TASK_RUNNING"):
        ledger.transition("tx", state)
    return ledger


def deliver(ledger, units=30):
    result = {"text": "delivery"}
    proof = sign(
        dict(transaction_id="tx", result_hash=hashlib.sha256(canonical(result)).hexdigest()),
        SEEDS["p"],
        "p",
        "Ed25519",
        domain="result",
    )
    return ledger.meter_verified("tx", units, result, proof)


def signatures(decision):
    return [sign(decision, SEEDS[k], k, "Ed25519", domain="decision") for k in ("a", "b")]


class StrictProfileTests(unittest.TestCase):
    def test_empty_delivery_refunds_and_partial_delivery_releases(self):
        for units in (0, 30):
            ledger = running()
            if units:
                deliver(ledger, units)
            ledger.transition("tx", "DISPUTED")
            decision = ledger.decision("tx", "d")
            ledger.resolve(decision, signatures(decision))
            self.assertEqual(
                ledger.snapshot()["balances"], {"buyer": 100 - units, "provider": units}
            )
            with self.assertRaises(ProtocolError):
                ledger.resolve(decision, signatures(decision))

    def test_quorum_evidence_and_bypass_rejected(self):
        ledger = running()
        deliver(ledger)
        ledger.transition("tx", "DISPUTED")
        d = ledger.decision("tx", "d")
        for sigs in ([], signatures(d)[:1], [signatures(d)[0]] * 2):
            with self.assertRaises(ProtocolError):
                ledger.resolve(d, sigs)
        bad = dict(d, evidence=[])
        with self.assertRaises(ProtocolError):
            ledger.resolve(bad, signatures(bad))
        with self.assertRaises(ProtocolError):
            ledger.transition("tx", "REFUNDED")
        self.assertEqual(ledger.snapshot()["held"], 100)

    def test_mock_and_unimplemented_proofs_fail_closed(self):
        ledger = running()
        for proof in (MockProof(), {"type": "MockProof"}, {"type": "TEE"}, {"type": "ZK"}):
            with self.assertRaises(ProtocolError):
                ledger.meter_verified("tx", 30, {}, proof)
        with self.assertRaises(ProtocolError):
            ledger.meter("tx", 30, "a" * 64)
        with self.assertRaises(ProtocolError):
            ledger.transition("tx", "PROOF_VERIFIED")

    def test_merkle_authenticated_inclusion_and_tampering(self):
        ledger = running()
        for _ in range(3):
            deliver(ledger, 10)
        ledger.transition("tx", "DISPUTED")
        d = ledger.decision("tx", "d")
        ledger.resolve(d, signatures(d))
        chain = ledger.chain("tx")
        receipt = ledger.receipt("tx", key=SEEDS["a"], key_id="a", algorithm="Ed25519")
        for index in range(3):
            proof = inclusion(chain, index)
            self.assertTrue(verify_meter_inclusion(receipt, chain, KEYS, chain[index], proof))
            bad = dict(chain[index], units=999)
            with self.assertRaises(ProtocolError):
                verify_meter_inclusion(receipt, chain, KEYS, bad, proof)
            forged = copy.deepcopy(proof)
            forged["siblings"][0] = "0" * 64
            with self.assertRaises(ProtocolError):
                verify_meter_inclusion(receipt, chain, KEYS, chain[index], forged)

    def test_signed_decision_survives_restart_and_rejects_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, cp = Path(tmp) / "journal", FileCheckpoint(Path(tmp) / "head", initialize=True)
            ledger = running(journal_path=path, checkpoint=cp)
            deliver(ledger)
            ledger.transition("tx", "DISPUTED")
            d = ledger.decision("tx", "d")
            sigs = signatures(d)
            tampered = copy.deepcopy(sigs)
            tampered[0]["signature"] = "0" * 128
            with self.assertRaises(ProtocolError):
                ledger.resolve(d, tampered)
            ledger.resolve(d, sigs)
            expected = ledger.snapshot()
            ledger.close()
            restored = StrictEscrowLedger(
                arbitrator_keys={k: KEYS[k] for k in ("a", "b")},
                provider_keys={"provider": {"p": KEYS["p"]}},
                quorum=2,
                journal_path=path,
                checkpoint=cp,
            )
            try:
                self.assertEqual(restored.snapshot(), expected)
                self.assertEqual(restored.decision_record("d")["decision"], d)
                with self.assertRaises(ProtocolError):
                    restored.resolve(d, sigs)
            finally:
                restored.close()

    def test_key_alias_cannot_inflate_quorum(self):
        with self.assertRaises(ProtocolError):
            StrictEscrowLedger(
                arbitrator_keys={"a": KEYS["a"], "alias": KEYS["a"]}, provider_keys={}, quorum=2
            )
