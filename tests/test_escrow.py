import unittest

from neuralclear.core import ProtocolError, Transaction, SettlementCredit, TransactionState
from neuralclear.escrow import EscrowLedger

# Independent transcription of SPEC 7 (not imported from the implementation).
EDGES = {
    "QUOTE_REQUESTED": ["QUOTE_ACCEPTED", "EXPIRED"],
    "QUOTE_ACCEPTED": ["TASK_SUBMITTED", "EXPIRED"],
    "TASK_SUBMITTED": ["TASK_RUNNING", "DISPUTED"],
    "TASK_RUNNING": ["RESULT_DELIVERED", "DISPUTED"],
    "RESULT_DELIVERED": ["PROOF_VERIFIED", "DISPUTED"],
    "PROOF_VERIFIED": ["SETTLED", "DISPUTED"],
    "SETTLED": ["DISPUTED"],
    "DISPUTED": ["REFUNDED", "SLASHED", "SETTLED"],
    "REFUNDED": [],
    "SLASHED": [],
    "EXPIRED": [],
}
PATH = [
    "QUOTE_ACCEPTED",
    "TASK_SUBMITTED",
    "TASK_RUNNING",
    "RESULT_DELIVERED",
    "PROOF_VERIFIED",
    "SETTLED",
]


def ledger_at(state="QUOTE_REQUESTED"):
    ledger = EscrowLedger()
    ledger.open_account("buyer", 100)
    ledger.open_account("provider")
    ledger.create("tx", "buyer", "provider", 50, 5)
    path = PATH[: PATH.index(state) + 1] if state in PATH else []
    if state in {"DISPUTED", "REFUNDED", "SLASHED"}:
        path = PATH[:3] + ["DISPUTED"]
        if state != "DISPUTED":
            path += [state]
    if state == "EXPIRED":
        path = ["EXPIRED"]
    for step in path:
        kwargs = {"amount": 50, "fee": 5} if step == "SETTLED" else {}
        if step == "SLASHED":
            kwargs = {"amount": 10}
        ledger.transition("tx", step, **kwargs)
        if step == "TASK_RUNNING":
            ledger.meter("tx", 50, "a" * 64)
    return ledger


class EscrowTests(unittest.TestCase):
    def test_all_state_pairs(self):
        for source in EDGES:
            for target in EDGES:
                with self.subTest(source=source, target=target):
                    ledger = ledger_at(source)
                    before = ledger.snapshot(), ledger.get("tx")
                    tx = Transaction(
                        "buyer",
                        "provider",
                        SettlementCredit(50),
                        "work",
                        state=TransactionState(source),
                    )
                    kwargs = {"amount": 20, "fee": 2} if target in {"SETTLED", "SLASHED"} else {}
                    if target in EDGES[source]:
                        tx.transition(TransactionState(target))
                        # Early disputes have no usage and therefore award zero.
                        if target in {"SLASHED", "SETTLED"} and not ledger.chain("tx"):
                            kwargs = {"amount": 0}
                        ledger.transition("tx", target, **kwargs)
                        snap = ledger.snapshot()
                        self.assertEqual(
                            sum(snap["balances"].values()) + snap["held"] + snap["fee_pool"], 100
                        )
                    else:
                        with self.assertRaises(ProtocolError):
                            tx.transition(TransactionState(target))
                        with self.assertRaises(ProtocolError):
                            ledger.transition("tx", target, **kwargs)
                        self.assertEqual((ledger.snapshot(), ledger.get("tx")), before)

    def test_partial_release_and_full_refund_after_settlement(self):
        ledger = ledger_at("PROOF_VERIFIED")
        ledger.transition("tx", "SETTLED", amount=30, fee=3)
        self.assertEqual(ledger.snapshot()["balances"], {"buyer": 67, "provider": 30})
        ledger.transition("tx", "DISPUTED")
        self.assertEqual(ledger.snapshot()["held"], 33)
        ledger.transition("tx", "REFUNDED")
        self.assertEqual(
            ledger.snapshot(),
            {
                "balances": {"buyer": 100, "provider": 0},
                "held": 0,
                "fee_pool": 0,
                "total_supply": 100,
            },
        )

    def test_frozen_escrow_cannot_execute_or_double_release(self):
        ledger = ledger_at("DISPUTED")
        with self.assertRaises(ProtocolError):
            ledger.transition("tx", "TASK_RUNNING")
        ledger.transition("tx", "SLASHED", amount=10, fee=0)
        self.assertEqual(ledger.snapshot()["balances"], {"buyer": 90, "provider": 10})
        with self.assertRaises(ProtocolError):
            ledger.transition("tx", "SLASHED", amount=10)

    def test_rejections_are_atomic(self):
        ledger = ledger_at("PROOF_VERIFIED")
        before = ledger.snapshot(), ledger.get("tx")
        for amount, fee in [(51, 0), (50, 6), (-1, 0), (True, 0), (1.5, 0)]:
            with self.subTest(amount=amount, fee=fee), self.assertRaises(ProtocolError):
                ledger.transition("tx", "SETTLED", amount=amount, fee=fee)
            self.assertEqual((ledger.snapshot(), ledger.get("tx")), before)

    def test_expiration_returns_reservation(self):
        ledger = ledger_at("QUOTE_ACCEPTED")
        self.assertEqual(ledger.snapshot()["held"], 55)
        ledger.transition("tx", "EXPIRED")
        self.assertEqual(ledger.snapshot()["balances"]["buyer"], 100)

    def test_insufficient_funding_and_freeze_rejected(self):
        ledger = ledger_at("QUOTE_ACCEPTED")
        ledger.create("second", "buyer", "provider", 50, 5)
        with self.assertRaises(ProtocolError):
            ledger.transition("second", "QUOTE_ACCEPTED")
        ledger = ledger_at("SETTLED")
        ledger.create("spent", "provider", "buyer", 50)
        ledger.transition("spent", "QUOTE_ACCEPTED")
        before = ledger.snapshot()
        with self.assertRaises(ProtocolError):
            ledger.transition("tx", "DISPUTED")
        self.assertEqual(ledger.snapshot(), before)

    def test_repeated_dispute_resolutions_conserve_funds(self):
        ledger = ledger_at("SETTLED")
        ledger.transition("tx", "DISPUTED")
        ledger.transition("tx", "SETTLED", amount=20, fee=2)
        ledger.transition("tx", "DISPUTED")
        ledger.transition("tx", "REFUNDED")
        self.assertEqual(ledger.get("tx")["refund"], 55)
        self.assertEqual(ledger.snapshot()["balances"], {"buyer": 100, "provider": 0})
        self.assertEqual(ledger.snapshot()["fee_pool"], 0)

    def test_observation_cannot_mutate_ledger(self):
        ledger = ledger_at("TASK_RUNNING")
        ledger.chain("tx")[0]["amount"] = 999
        ledger.get("tx")["history"].append("REFUNDED")
        ledger.snapshot()["balances"]["buyer"] = 999
        self.assertEqual(ledger.chain("tx")[0]["amount"], 50)
        self.assertEqual(ledger.get("tx")["state"], "TASK_RUNNING")
        self.assertEqual(ledger.snapshot()["balances"]["buyer"], 45)
