from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

from neuralclear import SettlementCredit, SpendingMandate
from neuralclear.core import ProtocolError

from .dashboard import register_dashboard_routes
from .ledger_store import ReferenceClearingService
from .registry import manifest_for
from .registry_store import build_default_registry_store
from .routes_registry import register_registry_routes

service = ReferenceClearingService(storage_path=os.environ.get("NEURALCLEAR_DB"))
registry_store = build_default_registry_store()

try:
    from fastapi import Depends, FastAPI, Header, HTTPException
except ImportError:  # pragma: no cover - keeps core tests dependency-free.
    Depends = None
    FastAPI = None
    Header = None
    HTTPException = None
    app = None
else:
    app = FastAPI(title="NeuralClear Reference Server", version="0.2.0-draft")


def _default_mandate() -> SpendingMandate:
    return SpendingMandate(
        owner="buyer.research",
        agent="buyer.research.agent",
        allowed_capabilities=["summarize.pdf"],
        max_per_task=SettlementCredit(100, "CC"),
        max_daily=SettlementCredit(1_000, "CC"),
        valid_until=(datetime.now(timezone.utc) + timedelta(days=1)).timestamp(),
        requires_human_approval_above=SettlementCredit(500, "CC"),
        signature="ed25519:demo",
    )


def _handle_error(exc: ProtocolError) -> None:
    if HTTPException is None:
        raise exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def _read_api_key() -> str:
    return os.environ.get(
        "NEURALCLEAR_READ_API_KEY",
        os.environ.get("NEURALCLEAR_API_KEY", "dev_neuralclear_read_key"),
    )


def _write_api_key() -> str:
    return os.environ.get(
        "NEURALCLEAR_WRITE_API_KEY",
        os.environ.get("NEURALCLEAR_API_KEY", "dev_neuralclear_key"),
    )


def _require_read_key(x_neuralclear_api_key: str | None = Header(default=None)) -> None:
    if x_neuralclear_api_key not in {_read_api_key(), _write_api_key()}:
        if HTTPException is None:
            raise ProtocolError("invalid or missing API key")
        raise HTTPException(status_code=401, detail="invalid or missing API key")


def _require_write_key(x_neuralclear_api_key: str | None = Header(default=None)) -> None:
    if x_neuralclear_api_key is None:
        if HTTPException is None:
            raise ProtocolError("invalid or missing API key")
        raise HTTPException(status_code=401, detail="invalid or missing API key")
    if x_neuralclear_api_key == _read_api_key():
        if HTTPException is None:
            raise ProtocolError("write API key required")
        raise HTTPException(status_code=403, detail="write API key required")
    if x_neuralclear_api_key != _write_api_key():
        if HTTPException is None:
            raise ProtocolError("invalid or missing API key")
        raise HTTPException(status_code=401, detail="invalid or missing API key")


if app is not None:
    write_protected = [Depends(_require_write_key)]

    @app.get("/")
    def index() -> dict[str, object]:
        return {
            "name": "NeuralClear Sandbox",
            "stage": "V0.4 developer preview draft",
            "docs": "/docs",
            "dashboard": "/dashboard/agents",
            "registry": "/registry/agents",
        }

    @app.get("/.well-known/neuralclear/agent.json")
    def get_agent_manifest() -> dict[str, object]:
        return manifest_for(service.registry.get("agent.pdf_summarizer"))

    @app.get("/health")
    def health() -> dict[str, str]:
        storage = "ok"
        if service.storage is not None:
            try:
                service.storage.connection.execute("SELECT 1")
            except Exception:
                storage = "error"
        return {"status": "ok", "service": "neuralclear", "storage": storage}

    @app.get("/version")
    def version() -> dict[str, str]:
        return {"service": "neuralclear", "version": "0.4.0-draft"}

    @app.post("/neuralclear/quote", dependencies=write_protected)
    def request_quote(body: dict[str, object]) -> dict[str, object]:
        try:
            return service.request_quote(
                provider=str(body.get("provider", "agent.pdf_summarizer")),
                capability=str(body.get("capability", "summarize.pdf")),
            )
        except ProtocolError as exc:
            _handle_error(exc)

    @app.post("/neuralclear/tasks", dependencies=write_protected)
    def submit_task(
        body: dict[str, object],
        idempotency_key: str | None = Header(default=None),
    ) -> dict[str, object]:
        try:
            mandate_body = body.get("mandate")
            mandate = _default_mandate()
            if isinstance(mandate_body, dict):
                mandate = SpendingMandate(
                    owner=str(mandate_body["owner"]),
                    agent=str(mandate_body["agent"]),
                    allowed_capabilities=list(mandate_body["allowed_capabilities"]),
                    max_per_task=SettlementCredit(**mandate_body["max_per_task"]),
                    max_daily=SettlementCredit(**mandate_body["max_daily"]),
                    valid_until=float(mandate_body["valid_until"]),
                    requires_human_approval_above=SettlementCredit(
                        **mandate_body["requires_human_approval_above"]
                    ),
                    signature=str(mandate_body["signature"]),
                )
            return service.submit_task(
                task_id=str(body.get("task_id", f"task_{uuid4().hex}")),
                quote_id=str(body["quote_id"]),
                buyer=str(body.get("buyer", "buyer.research")),
                provider=str(body.get("provider", "agent.pdf_summarizer")),
                payload=dict(body.get("payload", {})),
                mandate=mandate,
                idempotency_key=idempotency_key,
            )
        except (KeyError, ProtocolError) as exc:
            if "idempotency key conflict" in str(exc) and HTTPException is not None:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            _handle_error(ProtocolError(str(exc)))

    @app.get("/neuralclear/tasks/{task_id}")
    def get_task(task_id: str) -> dict[str, object]:
        try:
            return service.get_task(task_id)
        except ProtocolError as exc:
            _handle_error(exc)

    @app.post("/neuralclear/settlements")
    def create_settlement(body: dict[str, object]) -> dict[str, object]:
        try:
            return service.get_receipt_for_transaction(str(body["transaction_id"]))
        except (KeyError, ProtocolError) as exc:
            _handle_error(ProtocolError(str(exc)))

    @app.post("/neuralclear/disputes", dependencies=write_protected)
    def open_dispute(body: dict[str, object]) -> dict[str, object]:
        try:
            return service.open_dispute(
                transaction_id=str(body["transaction_id"]),
                opened_by=str(body.get("opened_by", "buyer.research")),
                reason=str(body.get("reason", "unspecified")),
            )
        except (KeyError, ProtocolError) as exc:
            _handle_error(ProtocolError(str(exc)))

    @app.get("/neuralclear/receipts/{receipt_id}")
    def get_receipt(receipt_id: str) -> dict[str, object]:
        try:
            return service.get_receipt(receipt_id)
        except ProtocolError as exc:
            _handle_error(exc)

    @app.get("/neuralclear/receipts")
    def list_receipts() -> list[dict[str, object]]:
        return service.list_receipts()

    @app.get("/neuralclear/balances")
    def get_balances() -> dict[str, object]:
        return service.balances_snapshot()

    register_registry_routes(app, registry_store, _handle_error, write_protected)
    register_dashboard_routes(app, service, registry_store)
