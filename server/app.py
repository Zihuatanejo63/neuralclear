from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from neuralclear import SettlementCredit, SpendingMandate
from neuralclear.core import ProtocolError

from .ledger_store import ReferenceClearingService
from .registry import manifest_for

service = ReferenceClearingService()

try:
    from fastapi import FastAPI, HTTPException
except ImportError:  # pragma: no cover - keeps core tests dependency-free.
    FastAPI = None
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


if app is not None:

    @app.get("/.well-known/neuralclear/agent.json")
    def get_agent_manifest() -> dict[str, object]:
        return manifest_for(service.registry.get("agent.pdf_summarizer"))

    @app.post("/neuralclear/quote")
    def request_quote(body: dict[str, object]) -> dict[str, object]:
        try:
            return service.request_quote(
                provider=str(body.get("provider", "agent.pdf_summarizer")),
                capability=str(body.get("capability", "summarize.pdf")),
            )
        except ProtocolError as exc:
            _handle_error(exc)

    @app.post("/neuralclear/tasks")
    def submit_task(body: dict[str, object]) -> dict[str, object]:
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
            )
        except (KeyError, ProtocolError) as exc:
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

    @app.post("/neuralclear/disputes")
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
