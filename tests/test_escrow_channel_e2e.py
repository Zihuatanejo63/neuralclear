import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from examples.escrow_channel_demo import run_branch, OWNER_KEYS, PUBLIC
from neuralclear.clearing import ClearingLedger
from neuralclear.core import ProtocolError
from neuralclear.verify import verify
from neuralclear.proofs import verify_result
from neuralclear.stripe_channel import NetSettlement, StripeChannel, StripeHTTP
from tests.test_escrow_journal import Checkpoint


class ChannelE2ETests(unittest.TestCase):
    def test_pending_payout_survives_restart_and_reconciles_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, cp = Path(tmp) / "ledger", Checkpoint()
            result = run_branch(journal_path=path, checkpoint=cp, payout_status="pending")
            self.assertEqual(result["ledger"].snapshot()["balances"]["@payout:normal"], 50)
            result["ledger"].close()
            ledger = ClearingLedger(
                provider_accounts={"provider": "acct_provider"},
                mandate_keys=OWNER_KEYS,
                journal_path=path,
                checkpoint=cp,
            )
            channel = StripeChannel(ledger, StripeHTTP("sk_test_fake", opener=result["fake"]))
            with self.assertRaises(ProtocolError):
                channel.payout("normal", idempotency_key="retry")
            with self.assertRaises(ProtocolError):
                ledger.create("steal", "@payout:normal", "buyer", 50)
            row = ledger.payout_record("normal")
            net = NetSettlement(**row["net"])
            payout_id = row["payout"]["id"]
            result["fake"].objects[payout_id]["status"] = "paid"
            channel.reconcile_payout(net, row["transfer"], payout_id)
            channel.reconcile_payout(net, row["transfer"], payout_id)
            self.assertEqual(ledger.snapshot()["total_supply"], 5)
            with self.assertRaises(ProtocolError):
                ledger.transition("normal", "DISPUTED")
            ledger.close()

    def check_branch(self, disputed):
        with tempfile.TemporaryDirectory() as tmp:
            root, checkpoint = Path(tmp), Checkpoint()
            outcome = run_branch(disputed, journal_path=root / "ledger", checkpoint=checkpoint)
            ledger, receipt = outcome["ledger"], outcome["receipt"]
            self.assertEqual(outcome["funded"]["held"], 55)
            self.assertEqual(outcome["funded"]["total_supply"], 55)
            self.assertEqual(receipt["amount"], 20 if disputed else 50)
            self.assertEqual(receipt["refund"], 33 if disputed else 0)
            self.assertEqual("DISPUTED" in receipt["history"], disputed)
            self.assertEqual(outcome["payout"]["amount"], receipt["amount"])
            proof = outcome["result"]["proof"]
            self.assertEqual(proof["result_hash"], receipt["result_hash"])
            with self.assertRaises(ProtocolError):
                verify_result(
                    {"summary": "tampered"},
                    proof,
                    receipt["transaction_id"],
                    {"provider": ("Ed25519", PUBLIC)},
                )
            self.assertEqual(ledger.snapshot()["balances"]["provider"], 0)
            self.assertEqual(ledger.snapshot()["total_supply"], 55 - receipt["amount"])
            calls = len(outcome["fake"].requests)
            with self.assertRaises(ProtocolError):
                outcome["channel"].payout(receipt["transaction_id"], idempotency_key="different")
            self.assertEqual(len(outcome["fake"].requests), calls)
            expected = ledger.snapshot()
            ledger.close()
            restored = ClearingLedger(
                provider_accounts={"provider": "acct_provider"},
                mandate_keys=OWNER_KEYS,
                journal_path=root / "ledger",
                checkpoint=checkpoint,
            )
            self.assertEqual(restored.snapshot(), expected)
            self.assertEqual(restored.chain(receipt["transaction_id"]), outcome["chain"])
            restored.close()
            (root / "receipt.json").write_text(json.dumps(receipt))
            (root / "chain.json").write_text(json.dumps(outcome["chain"]))
            (root / "public.key").write_bytes(PUBLIC)
            command = [
                sys.executable,
                "-m",
                "neuralclear.verify",
                str(root / "receipt.json"),
                str(root / "chain.json"),
                "--key-id",
                "clearing",
                "--algorithm",
                "Ed25519",
                "--key-file",
                str(root / "public.key"),
            ]
            process = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertEqual(process.stdout.strip(), "VALID")
            receipt["refund"] += 1
            with self.assertRaises(ProtocolError):
                verify(receipt, outcome["chain"], {"clearing": ("Ed25519", PUBLIC)})

    def test_normal_funding_metering_payout_and_independent_verification(self):
        self.check_branch(False)

    def test_dispute_partial_award_refund_and_independent_verification(self):
        self.check_branch(True)
