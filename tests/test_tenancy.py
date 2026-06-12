"""Tenancy: isolation, metering, operator invoicing."""
from __future__ import annotations
import unittest
from datetime import datetime, timezone
from neuralclear.core import MockProof, ProtocolError, Quote, ResourceUnit, SettlementCredit, TaskResult
from neuralclear.tenancy import TenantHub

def _clear_once(tenant, price=10):
    ledger = tenant.clearing.ledger
    if "buyer" not in ledger.balances:
        ledger.open_account("buyer", SettlementCredit(100))
        ledger.open_account("prov", SettlementCredit(0))
    q = Quote(provider="prov", capability="echo", resource_estimate=ResourceUnit(1,"calls"),
              settlement_price=SettlementCredit(price), expires_at=float("inf"))
    tenant.clearing.clear("buyer","agent",q,
        lambda: TaskResult("",{"ok":1},[ResourceUnit(1,"calls")],SettlementCredit(price),MockProof()))

class TenancyTests(unittest.TestCase):
    def test_isolation_and_auth(self):
        hub = TenantHub(price_per_settlement_cents=50)
        a, b = hub.create_tenant("Acme"), hub.create_tenant("Bolt")
        _clear_once(a)
        self.assertEqual(a.clearing.ledger.balance_of("prov"), 10)
        self.assertEqual(b.clearing.ledger.balance_of("prov"), 0)  # isolated
        self.assertIs(hub.by_key(a.api_key), a)
        with self.assertRaises(ProtocolError): hub.by_key("nck_wrong")

    def test_metering_and_invoice(self):
        hub = TenantHub(price_per_settlement_cents=50)
        t = hub.create_tenant("Acme")
        for _ in range(3): _clear_once(t)
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        self.assertEqual(hub.settlements(t.tenant_id, month), 3)
        inv = hub.invoice(t.tenant_id, month)
        self.assertEqual(inv["amount_due_cents"], 150)
        report = hub.revenue_report(month)
        self.assertEqual(report["total_due_cents"], 150)

    def test_key_rotation(self):
        hub = TenantHub()
        t = hub.create_tenant("Acme"); old = t.api_key
        new = hub.rotate_key(t.tenant_id)
        self.assertIs(hub.by_key(new), t)
        with self.assertRaises(ProtocolError): hub.by_key(old)

if __name__ == "__main__":
    unittest.main()
