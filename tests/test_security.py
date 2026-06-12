"""Adversarial regression tests: the vulnerabilities found in audit must stay fixed."""
from __future__ import annotations
import json, threading, unittest, urllib.request
from neuralclear.clearing import ClearingService, EscrowLedger, FeePolicy, FeeSchedule
from neuralclear.core import MockProof, ProtocolError, Quote, ResourceUnit, SettlementCredit, TaskResult
from neuralclear.gateway import ClearingGateway
from neuralclear.httpwire import ProviderHTTPServer
from neuralclear.provider import ProviderAgent


def _quote(price=30):
    return Quote(provider="pr", capability="x", resource_estimate=ResourceUnit(1, "u"),
                 settlement_price=SettlementCredit(price), expires_at=float("inf"))


class CrashRefundTests(unittest.TestCase):
    def test_provider_crash_refunds_escrow(self):
        L = EscrowLedger(); L.open_account("o", SettlementCredit(100)); L.open_account("pr", SettlementCredit(0))
        svc = ClearingService(ledger=L, fees=FeeSchedule(FeePolicy(bps=0)))
        def boom(): raise RuntimeError("provider crashed")
        with self.assertRaises(ProtocolError):
            svc.clear("o", "a", _quote(30), boom)
        self.assertEqual(L.balance_of("o"), 100)   # fully restored
        self.assertEqual(L.escrow_total(), 0)      # nothing stranded
        self.assertTrue(L.verify_zero_sum())


class ConcurrencyTests(unittest.TestCase):
    def test_concurrent_clears_cannot_overspend(self):
        p = ProviderAgent("agent.slow")
        @p.capability("slow.task", price=60, resource_estimate=1, resource_unit="calls")
        def slow(payload):
            import time; time.sleep(0.12); return {"ok": 1}
        psrv = ProviderHTTPServer(p).start()
        L = EscrowLedger(); L.open_account("owner", SettlementCredit(100)); L.open_account("agent.slow", SettlementCredit(0))
        gw = ClearingGateway(clearing=ClearingService(ledger=L, fees=FeeSchedule(FeePolicy(bps=0))), api_key="k").start()
        res = {}
        def fire(i):
            try:
                req = urllib.request.Request(gw.url + "/v1/clear", method="POST",
                    headers={"Content-Type": "application/json", "X-NeuralClear-Api-Key": "k"},
                    data=json.dumps({"buyer_owner": "owner", "provider_url": psrv.url,
                                     "capability": "slow.task", "payload": {}}).encode())
                with urllib.request.urlopen(req, timeout=5) as r: res[i] = json.loads(r.read())
            except Exception as e: res[i] = {"error": str(e)}
        ts = [threading.Thread(target=fire, args=(i,)) for i in range(2)]
        [t.start() for t in ts]; [t.join() for t in ts]
        gw.stop(); psrv.stop()
        self.assertGreaterEqual(L.balance_of("owner"), 0)   # never negative
        self.assertTrue(L.verify_zero_sum())                # invariant holds
        self.assertLessEqual(sum(1 for r in res.values() if "receipt_id" in r), 1)  # at most one 60-clear


class GatewayAuthTests(unittest.TestCase):
    def test_timing_safe_compare_used(self):
        import inspect
        from neuralclear import gateway
        self.assertIn("compare_digest", inspect.getsource(gateway))


if __name__ == "__main__":
    unittest.main()
