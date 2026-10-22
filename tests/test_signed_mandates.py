from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest

from neuralclear.core import ProtocolError
from neuralclear.escrow import EscrowLedger
from neuralclear.mandates import issue_mandate
from tests.test_escrow_journal import Checkpoint

KEYS = {"owner-key": ("buyer", "HMAC-SHA256", b"owner-secret")}


def mandate(**overrides):
    body = dict(
        mandate_id="m1",
        owner="buyer",
        agent="delegate",
        currency="CC",
        allowed_capabilities=["summarize"],
        max_per_task=60,
        max_daily=60,
        max_total=100,
        valid_until=1000,
        requires_human_approval_above=60,
    )
    body.update(overrides)
    return issue_mandate(body, b"owner-secret", "owner-key")


class SignedMandateTests(unittest.TestCase):
    def ledger(self, **kwargs):
        ledger = EscrowLedger(mandate_keys=KEYS, clock=lambda: 100, **kwargs)
        ledger.open_account("buyer", 1000)
        ledger.open_account("provider")
        ledger.register_mandate(mandate())
        return ledger

    def bind(self, ledger, tx="tx"):
        ledger.create(tx, "buyer", "provider", 50, 5)
        ledger.authorize(tx, "m1", "delegate", "summarize")

    def test_atomic_concurrent_budget_reservations(self):
        ledger = self.ledger()
        for i in range(20):
            self.bind(ledger, str(i))

        def reserve(i):
            try:
                ledger.transition(str(i), "QUOTE_ACCEPTED")
                return True
            except ProtocolError:
                return False

        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(reserve, range(20))), 1)
        self.assertEqual(ledger.mandate_usage("m1"), {"reserved": 55, "spent": 0})
        self.assertEqual(ledger.snapshot()["held"], 55)

    def test_revocation_checked_before_execution_and_meter(self):
        ledger = self.ledger()
        self.bind(ledger)
        ledger.transition("tx", "QUOTE_ACCEPTED")
        ledger.transition("tx", "TASK_SUBMITTED")
        ledger.revoke_mandate("m1")
        with self.assertRaisesRegex(ProtocolError, "revoked"):
            ledger.transition("tx", "TASK_RUNNING")
        ledger.transition("tx", "DISPUTED")
        ledger.transition("tx", "REFUNDED")
        self.assertEqual(ledger.mandate_usage("m1"), {"reserved": 0, "spent": 0})

    def test_signature_context_expiry_and_limits(self):
        for override in (
            {"agent": "other"},
            {"owner": "other"},
            {"currency": "USD"},
            {"valid_until": 100},
            {"max_per_task": 54},
            {"requires_human_approval_above": 54},
            {"allowed_capabilities": ["other"]},
        ):
            with self.subTest(override=override):
                ledger = EscrowLedger(mandate_keys=KEYS, clock=lambda: 100)
                ledger.open_account("buyer", 100)
                ledger.open_account("provider")
                with self.assertRaises(ProtocolError):
                    ledger.register_mandate(mandate(**override))
                    self.bind(ledger)
        bad = mandate()
        bad["max_daily"] += 1
        with self.assertRaises(ProtocolError):
            self.ledger().register_mandate(bad)

    def test_partial_settlement_consumes_actual_budget(self):
        ledger = self.ledger()
        self.bind(ledger)
        for state in ("QUOTE_ACCEPTED", "TASK_SUBMITTED", "TASK_RUNNING"):
            ledger.transition("tx", state)
        ledger.meter("tx", 30, "a" * 64)
        ledger.transition("tx", "DISPUTED")
        ledger.transition("tx", "SETTLED", amount=20, fee=2)
        self.assertEqual(ledger.mandate_usage("m1"), {"reserved": 0, "spent": 22})

    def test_revocation_and_reservations_survive_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, cp = Path(tmp) / "ledger", Checkpoint()
            ledger = self.ledger(journal_path=path, checkpoint=cp)
            self.bind(ledger)
            ledger.transition("tx", "QUOTE_ACCEPTED")
            ledger.revoke_mandate("m1")
            ledger.close()
            restored = EscrowLedger(mandate_keys=KEYS, journal_path=path, checkpoint=cp)
            self.assertEqual(restored.mandate_usage("m1")["reserved"], 55)
            with self.assertRaisesRegex(ProtocolError, "revoked"):
                restored.transition("tx", "TASK_SUBMITTED")
            restored.close()

    def test_revoked_running_task_cannot_meter(self):
        ledger = self.ledger()
        self.bind(ledger)
        ledger.transition("tx", "QUOTE_ACCEPTED")
        ledger.start_task("tx")
        ledger.revoke_mandate("m1")
        with self.assertRaisesRegex(ProtocolError, "revoked"):
            ledger.meter("tx", 1, "a" * 64)
        self.assertEqual(ledger.chain("tx"), [])

    def test_expiry_checked_again_after_reservation(self):
        ledger = self.ledger()
        self.bind(ledger)
        ledger.transition("tx", "QUOTE_ACCEPTED")
        ledger._clock = lambda: 1000
        with self.assertRaisesRegex(ProtocolError, "expired"):
            ledger.start_task("tx")
        self.assertEqual(ledger.get("tx")["state"], "QUOTE_ACCEPTED")

    def test_total_budget_across_days(self):
        ledger = self.ledger()
        ledger.register_mandate(mandate(mandate_id="long", valid_until=999999))
        ledger.create("a", "buyer", "provider", 50, 5)
        ledger.authorize("a", "long", "delegate", "summarize")
        ledger.transition("a", "QUOTE_ACCEPTED")
        ledger._clock = lambda: 86500
        ledger.create("b", "buyer", "provider", 50, 5)
        ledger.authorize("b", "long", "delegate", "summarize")
        with self.assertRaisesRegex(ProtocolError, "total limit"):
            ledger.transition("b", "QUOTE_ACCEPTED")
        self.assertEqual(ledger.mandate_usage("long")["reserved"], 55)
