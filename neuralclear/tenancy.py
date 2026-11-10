"""Tenancy and operator usage metering.

Each tenant has an isolated clearing ledger and its own API key. The gateway
resolves a request key to that tenant. Keys are hashed at rest. Raw keys stay
in memory only for the process that just issued or rotated them.

Protocol credits on a tenant ledger are not customer funds. Fiat settlement
is not implemented here.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .clearing import (
    EVENT_RECEIPT_CREATED,
    ClearingService,
    Dispute,
    EscrowLedger,
    FeeSchedule,
    ReceiptSigner,
)
from .core import ProtocolError, SettlementCredit, Transaction, TransactionState
from .netting import ChannelState, NettingChannel, NettingService, UsageRecord
from .runtime_config import DEV_RECEIPT_SECRET
from .tenant_store import TenantSnapshot, TenantStore


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


@dataclass
class Tenant:
    tenant_id: str
    name: str
    api_key: str = field(repr=False)
    clearing: ClearingService = field(repr=False)
    key_hash: str = field(default="", repr=False)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    netting: NettingService | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not self.key_hash and self.api_key:
            self.key_hash = hash_api_key(self.api_key)
        if self.netting is None:
            self.netting = NettingService(self.clearing)


class TenantHub:
    """Operator control plane: tenants, isolation, metering, invoicing."""

    def __init__(
        self,
        price_per_settlement_cents: int = 0,
        fees: FeeSchedule | None = None,
        store_path: str | Path | None = None,
        receipt_secret: str | None = None,
        signer: object | None = None,
    ) -> None:
        self.price_per_settlement_cents = price_per_settlement_cents
        self._fees = fees
        if signer is not None:
            self._signer = signer
            self.receipt_secret = ""
        else:
            self.receipt_secret = receipt_secret if receipt_secret is not None else DEV_RECEIPT_SECRET
            self._signer = ReceiptSigner(self.receipt_secret)
        self._tenants: dict[str, Tenant] = {}
        self._by_hash: dict[str, Tenant] = {}
        self.usage: dict[str, dict[str, int]] = {}
        self.store = TenantStore(store_path) if store_path is not None else None
        if self.store is not None:
            for tenant_id in self.store.list_ids():
                self._hydrate(tenant_id)

    def tenant_count(self) -> int:
        return len(self._tenants)

    def create_tenant(self, name: str, api_key: str | None = None) -> Tenant:
        cleaned = str(name).strip()
        if not cleaned:
            raise ProtocolError("tenant name is required")
        raw_key = api_key if api_key is not None else f"nck_{secrets.token_hex(16)}"
        if not isinstance(raw_key, str) or not raw_key:
            raise ProtocolError("invalid api key")
        digest = hash_api_key(raw_key)
        if digest in self._by_hash:
            raise ProtocolError("api key already in use")
        if self.store is not None and self.store.tenant_id_for_hash(digest) is not None:
            raise ProtocolError("api key already in use")
        tenant = Tenant(
            tenant_id=f"ten_{secrets.token_hex(6)}",
            name=cleaned,
            api_key=raw_key,
            clearing=self._new_clearing(),
            key_hash=digest,
        )
        self._tenants[tenant.tenant_id] = tenant
        self._by_hash[digest] = tenant
        self.usage[tenant.tenant_id] = {}
        self._watch(tenant)
        if self.store is not None:
            try:
                self.store.insert(self._snapshot(tenant))
            except ValueError as exc:
                self._tenants.pop(tenant.tenant_id, None)
                self._by_hash.pop(digest, None)
                self.usage.pop(tenant.tenant_id, None)
                raise ProtocolError("api key already in use") from exc
        return tenant

    def ensure_bootstrap(self, name: str, api_key: str) -> Tenant:
        try:
            return self.by_key(api_key)
        except ProtocolError:
            return self.create_tenant(name, api_key=api_key)

    def rotate_key(self, tenant_id: str) -> str:
        tenant = self._get(tenant_id)
        new_key = f"nck_{secrets.token_hex(16)}"
        new_hash = hash_api_key(new_key)
        old_hash = tenant.key_hash
        self._by_hash.pop(old_hash, None)
        tenant.api_key = new_key
        tenant.key_hash = new_hash
        self._by_hash[new_hash] = tenant
        if self.store is not None:
            try:
                self.store.update_key_hash(tenant_id, new_hash)
            except KeyError as exc:
                raise ProtocolError("unknown tenant") from exc
            except ValueError as exc:
                self._by_hash.pop(new_hash, None)
                tenant.api_key = ""
                tenant.key_hash = old_hash
                if old_hash:
                    self._by_hash[old_hash] = tenant
                raise ProtocolError("api key already in use") from exc
        return new_key

    def by_key(self, api_key: str) -> Tenant:
        if not isinstance(api_key, str) or not api_key:
            raise ProtocolError("invalid api key")
        digest = hash_api_key(api_key)
        if self.store is not None:
            tenant_id = self.store.tenant_id_for_hash(digest)
            if tenant_id is None:
                self._drop_hash(digest)
                raise ProtocolError("invalid api key")
            tenant = self._tenants.get(tenant_id)
            if tenant is None:
                tenant = self._hydrate(tenant_id)
            elif not hmac.compare_digest(tenant.key_hash, digest):
                self._by_hash.pop(tenant.key_hash, None)
                tenant.key_hash = digest
                tenant.api_key = ""
                self._by_hash[digest] = tenant
            if tenant is None or not hmac.compare_digest(tenant.key_hash, digest):
                raise ProtocolError("invalid api key")
            return tenant
        tenant = self._by_hash.get(digest)
        if tenant is None or not hmac.compare_digest(tenant.key_hash, digest):
            raise ProtocolError("invalid api key")
        return tenant

    def persist(self, tenant: Tenant) -> None:
        if self.store is None:
            return
        self.store.save_state(self._snapshot(tenant))

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
        if tenant is None and self.store is not None:
            loaded = self.store.load(tenant_id)
            if loaded is not None:
                tenant = self._hydrate(tenant_id)
        if tenant is None:
            raise ProtocolError("unknown tenant")
        return tenant

    def _new_clearing(self) -> ClearingService:
        return ClearingService(ledger=EscrowLedger(), fees=self._fees, signer=self._signer)

    def _watch(self, tenant: Tenant) -> None:
        def on_receipt(_event: str, _payload: dict[str, object]) -> None:
            month = datetime.now(timezone.utc).strftime("%Y-%m")
            bucket = self.usage.setdefault(tenant.tenant_id, {})
            bucket[month] = bucket.get(month, 0) + 1
            self.persist(tenant)

        tenant.clearing.events.subscribe(EVENT_RECEIPT_CREATED, on_receipt)

    def _drop_hash(self, digest: str) -> None:
        tenant = self._by_hash.pop(digest, None)
        if tenant is not None and tenant.key_hash and hmac.compare_digest(tenant.key_hash, digest):
            tenant.key_hash = ""
            tenant.api_key = ""

    def _hydrate(self, tenant_id: str) -> Tenant:
        if self.store is None:
            raise ProtocolError("unknown tenant")
        snap = self.store.load(tenant_id)
        if snap is None:
            raise ProtocolError("unknown tenant")
        clearing = self._new_clearing()
        _apply_snapshot(clearing, snap)
        netting = NettingService(clearing)
        _apply_channels(clearing, netting, snap.channels)
        created = datetime.fromisoformat(snap.created_at)
        tenant = Tenant(
            tenant_id=snap.tenant_id,
            name=snap.name,
            api_key="",
            clearing=clearing,
            key_hash=snap.key_hash,
            created_at=created,
            netting=netting,
        )
        self._tenants[tenant.tenant_id] = tenant
        if tenant.key_hash:
            self._by_hash[tenant.key_hash] = tenant
        self.usage[tenant.tenant_id] = dict(snap.usage)
        self._watch(tenant)
        return tenant

    def _snapshot(self, tenant: Tenant) -> TenantSnapshot:
        ledger = tenant.clearing.ledger
        escrow = ledger.escrow if isinstance(ledger, EscrowLedger) else {}
        netting = tenant.netting
        channels: dict[str, dict[str, object]] = {}
        if netting is not None:
            for channel_id, channel in netting.channels.items():
                channels[channel_id] = {
                    "buyer": channel.buyer,
                    "provider": channel.provider,
                    "deposit": channel.deposit,
                    "fee": channel.fee,
                    "channel_id": channel.channel_id,
                    "state": channel.state.value,
                    "opened_at": channel.opened_at.isoformat(),
                    "records": [record.to_json() for record in channel.records],
                    "transaction": channel.transaction.to_json(),
                }
        return TenantSnapshot(
            tenant_id=tenant.tenant_id,
            name=tenant.name,
            key_hash=tenant.key_hash,
            created_at=tenant.created_at.isoformat(),
            usage=dict(self.usage.get(tenant.tenant_id, {})),
            balances=dict(ledger.balances),
            escrow=dict(escrow),
            fee_pool=ledger.fee_pool,
            total_supply=ledger.total_supply,
            receipts=dict(tenant.clearing.receipts),
            disputes={did: dispute.to_json() for did, dispute in tenant.clearing.disputes.items()},
            transactions={
                tx_id: transaction.to_json()
                for tx_id, transaction in tenant.clearing._transactions.items()
            },
            channels=channels,
        )


def _apply_snapshot(clearing: ClearingService, snap: TenantSnapshot) -> None:
    ledger = clearing.ledger
    ledger.balances = dict(snap.balances)
    if isinstance(ledger, EscrowLedger):
        ledger.escrow = dict(snap.escrow)
    ledger.fee_pool = snap.fee_pool
    ledger.total_supply = snap.total_supply
    clearing.receipts = dict(snap.receipts)
    clearing.disputes = {
        dispute_id: _dispute_from_json(body) for dispute_id, body in snap.disputes.items()
    }
    clearing._transactions = {
        tx_id: _transaction_from_json(body) for tx_id, body in snap.transactions.items()
    }


def _apply_channels(
    clearing: ClearingService,
    netting: NettingService,
    channels: dict[str, dict[str, object]],
) -> None:
    for channel_id, body in channels.items():
        tx_body = body.get("transaction")
        if not isinstance(tx_body, dict):
            continue
        tx_id = str(tx_body["transaction_id"])
        transaction = clearing._transactions.get(tx_id)
        if transaction is None:
            transaction = _transaction_from_json(tx_body)
            clearing._transactions[tx_id] = transaction
        records: list[UsageRecord] = []
        raw_records = body.get("records")
        if isinstance(raw_records, list):
            for item in raw_records:
                if isinstance(item, dict):
                    records.append(_usage_from_json(item))
        opened = body.get("opened_at")
        channel = NettingChannel(
            buyer=str(body["buyer"]),
            provider=str(body["provider"]),
            deposit=int(body["deposit"]),  # type: ignore[arg-type]
            fee=int(body["fee"]),  # type: ignore[arg-type]
            transaction=transaction,
            channel_id=str(body.get("channel_id", channel_id)),
            records=records,
            state=ChannelState(str(body["state"])),
            opened_at=datetime.fromisoformat(str(opened)) if opened else datetime.now(timezone.utc),
        )
        netting.channels[channel.channel_id] = channel


def _transaction_from_json(body: dict[str, object]) -> Transaction:
    amount = body["amount"]
    fee = body.get("fee")
    if not isinstance(amount, dict):
        raise ProtocolError("invalid transaction snapshot")
    if not isinstance(fee, dict):
        fee = {"amount": 0, "currency": amount.get("currency", "CC")}
    settled = body.get("settled_at")
    quote_id = body.get("quote_id")
    authorized = body.get("authorized_agent")
    return Transaction(
        sender=str(body["sender"]),
        receiver=str(body["receiver"]),
        amount=SettlementCredit(int(amount["amount"]), str(amount.get("currency", "CC"))),
        fee=SettlementCredit(int(fee["amount"]), str(fee.get("currency", "CC"))),
        capability=str(body["capability"]),
        quote_id=str(quote_id) if quote_id else None,
        authorized_agent=str(authorized) if authorized else None,
        transaction_id=str(body["transaction_id"]),
        state=TransactionState(str(body["state"])),
        settled_at=datetime.fromisoformat(str(settled)) if settled else None,
    )


def _dispute_from_json(body: dict[str, object]) -> Dispute:
    evidence = body.get("evidence")
    resolved = body.get("resolved_at")
    provider_amount = body.get("provider_amount")
    return Dispute(
        transaction_id=str(body["transaction_id"]),
        raised_by=str(body["raised_by"]),
        reason=str(body["reason"]),
        evidence=evidence if isinstance(evidence, dict) else {},
        dispute_id=str(body["dispute_id"]),
        opened_at=datetime.fromisoformat(str(body["opened_at"])),
        resolution=str(body["resolution"]) if body.get("resolution") else None,
        resolved_by=str(body["resolved_by"]) if body.get("resolved_by") else None,
        resolved_at=datetime.fromisoformat(str(resolved)) if resolved else None,
        provider_amount=int(provider_amount) if provider_amount is not None else None,
    )


def _usage_from_json(body: dict[str, object]) -> UsageRecord:
    return UsageRecord(
        sequence=int(body["sequence"]),  # type: ignore[arg-type]
        capability=str(body["capability"]),
        amount=int(body["amount"]),  # type: ignore[arg-type]
        payload_hash=str(body["payload_hash"]),
        prev_hash=str(body["prev_hash"]),
        recorded_at=str(body["recorded_at"]),
    )
