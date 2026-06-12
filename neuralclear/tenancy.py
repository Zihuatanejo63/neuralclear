"""Tenancy + operator billing: from protocol fees to company revenue.

The hosted gateway charges per settlement. That requires what this module
provides: isolated tenants (own ledger, own API keys) and operator-side
usage metering that turns clearing activity into a monthly invoice.

    hub = TenantHub(price_per_settlement_cents=50)
    acme = hub.create_tenant("Acme Robotics")
    tenant = hub.by_key(acme.api_key)         # gateway auth -> tenant routing
    tenant.clearing.clear(...)                # normal clearing, auto-metered
    hub.invoice(acme.tenant_id, "2026-06")    # -> the bill
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .clearing import EVENT_RECEIPT_CREATED, ClearingService, EscrowLedger, FeeSchedule
from .core import ProtocolError


@dataclass
class Tenant:
    tenant_id: str
    name: str
    api_key: str
    clearing: ClearingService
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class TenantHub:
    """Operator control plane: tenants, isolation, metering, invoicing."""

    def __init__(self, price_per_settlement_cents: int = 0, fees: FeeSchedule | None = None) -> None:
        self.price_per_settlement_cents = price_per_settlement_cents
        self._fees = fees
        self._tenants: dict[str, Tenant] = {}
        self._by_key: dict[str, Tenant] = {}
        # usage[tenant_id][YYYY-MM] = settlements cleared
        self.usage: dict[str, dict[str, int]] = {}

    # -- lifecycle ----------------------------------------------------------
    def create_tenant(self, name: str) -> Tenant:
        tenant_id = f"ten_{secrets.token_hex(6)}"
        api_key = f"nck_{secrets.token_hex(16)}"
        clearing = ClearingService(ledger=EscrowLedger(), fees=self._fees)
        tenant = Tenant(tenant_id=tenant_id, name=name, api_key=api_key, clearing=clearing)
        self._tenants[tenant_id] = tenant
        self._by_key[api_key] = tenant
        self.usage[tenant_id] = {}

        def on_receipt(_event: str, _payload: dict[str, object]) -> None:
            month = datetime.now(timezone.utc).strftime("%Y-%m")
            self.usage[tenant_id][month] = self.usage[tenant_id].get(month, 0) + 1

        clearing.events.subscribe(EVENT_RECEIPT_CREATED, on_receipt)
        return tenant

    def rotate_key(self, tenant_id: str) -> str:
        tenant = self._get(tenant_id)
        del self._by_key[tenant.api_key]
        tenant.api_key = f"nck_{secrets.token_hex(16)}"
        self._by_key[tenant.api_key] = tenant
        return tenant.api_key

    # -- auth routing (gateway calls this per request) ------------------------
    def by_key(self, api_key: str) -> Tenant:
        tenant = self._by_key.get(api_key)
        if tenant is None:
            raise ProtocolError("invalid api key")
        return tenant

    # -- billing --------------------------------------------------------------
    def settlements(self, tenant_id: str, month: str) -> int:
        return self.usage.get(tenant_id, {}).get(month, 0)

    def invoice(self, tenant_id: str, month: str) -> dict[str, object]:
        tenant = self._get(tenant_id)
        count = self.settlements(tenant_id, month)
        return {
            "invoice_id": f"inv_{tenant_id}_{month}",
            "tenant": tenant.name,
            "period": month,
            "settlements": count,
            "unit_price_cents": self.price_per_settlement_cents,
            "amount_due_cents": count * self.price_per_settlement_cents,
            # hand this dict to Stripe metered billing / Alipay corporate / your ERP
        }

    def revenue_report(self, month: str) -> dict[str, object]:
        lines = [self.invoice(tenant_id, month) for tenant_id in self._tenants]
        return {
            "period": month,
            "tenants": len(lines),
            "total_settlements": sum(int(line["settlements"]) for line in lines),
            "total_due_cents": sum(int(line["amount_due_cents"]) for line in lines),
            "lines": lines,
        }

    def _get(self, tenant_id: str) -> Tenant:
        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            raise ProtocolError("unknown tenant")
        return tenant
