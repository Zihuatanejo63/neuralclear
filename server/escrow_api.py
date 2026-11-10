"""Explicit escrow-v1 app factory. Legacy server.app routes remain unchanged.

Deploy separately or mount under /escrow. The ledger must be
neuralclear.escrow (including ClearingLedger). The credit ledger is rejected.
This module does not call Stripe. Operator supplies keys, ledger and provider
configuration; this module never supplies a default production key.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from neuralclear.core import ProtocolError
from neuralclear.production_guard import assert_escrow_app_ready
from neuralclear.secretcmp import const_equal
from neuralclear.wire import PROFILE, load_json
from neuralclear.escrow_channel import EscrowWorkflow

VERSION = "1"
HEADERS = {"X-NeuralClear-Profile": PROFILE, "X-NeuralClear-Version": VERSION}


def error_code(message):
    mappings = [
        ("quote expired", "QUOTE_EXPIRED"),
        ("insufficient", "INSUFFICIENT_CREDIT"),
        ("mandate expired", "MANDATE_EXPIRED"),
        ("mandate revoked", "MANDATE_REVOKED"),
        ("limit", "MANDATE_LIMIT_EXCEEDED"),
        ("human approval", "MANDATE_LIMIT_EXCEEDED"),
        ("currency", "MANDATE_CURRENCY_MISMATCH"),
        ("capability", "CAPABILITY_NOT_ALLOWED"),
        ("signature", "PROOF_VERIFICATION_FAILED"),
        ("proof", "PROOF_VERIFICATION_FAILED"),
        ("algorithm", "PROOF_VERIFICATION_FAILED"),
        ("invariant", "LEDGER_INVARIANT_FAILED"),
        ("invalid parties", "UNKNOWN_AGENT"),
        ("unknown provider", "UNKNOWN_AGENT"),
        ("unknown escrow", "UNKNOWN_TRANSACTION"),
        ("transition", "INVALID_STATE_TRANSITION"),
        ("state", "INVALID_STATE_TRANSITION"),
        ("duplicate", "CONFLICT"),
        ("conflict", "CONFLICT"),
        ("mandate", "MANDATE_INVALID"),
    ]
    return next((code for fragment, code in mappings if fragment in message), "INVALID_REQUEST")


def create_escrow_app(
    ledger,
    *,
    write_key,
    receipt_key,
    receipt_key_id,
    algorithm="Ed25519",
    mode=None,
    signer=None,
):
    from neuralclear.clearing import ClearingService
    from neuralclear.clearing import EscrowLedger as CreditLedger
    from neuralclear.escrow import EscrowLedger as FiatLedger
    import os

    if isinstance(ledger, (CreditLedger, ClearingService)) or not isinstance(ledger, FiatLedger):
        raise ProtocolError(
            "escrow HTTP app requires neuralclear.escrow; it cannot attach the credit ledger"
        )
    if not write_key:
        raise ValueError("explicit write key required")
    resolved_mode = mode or os.environ.get("NEURALCLEAR_MODE", "sandbox")
    if resolved_mode == "production":
        assert_escrow_app_ready(write_key=write_key, signer=signer, algorithm=algorithm)
    app = FastAPI(title="NeuralClear escrow-v1", version=VERSION)
    workflow = EscrowWorkflow(ledger)

    def failure(code, status=400):
        return JSONResponse(
            {"error": {"code": code}, "profile": PROFILE, "version": VERSION},
            status_code=status,
            headers=HEADERS,
        )

    @app.middleware("http")
    async def negotiate(request: Request, call_next):
        if request.url.path != "/.well-known/neuralclear/agent.json":
            if (
                request.headers.get("X-NeuralClear-Profile") != PROFILE
                or request.headers.get("X-NeuralClear-Version") != VERSION
            ):
                return failure("UNSUPPORTED_VERSION", 406)
        provided_key = request.headers.get("X-NeuralClear-API-Key")
        needs_key = resolved_mode == "production" or request.method != "GET"
        if needs_key and not const_equal(provided_key, write_key):
            return failure("UNAUTHORIZED", 401)
        if request.method == "POST":
            try:
                body = load_json((await request.body()).decode("utf-8"))
                required = {
                    "/neuralclear/quote": {"quote", "mandate", "agent", "capability"},
                    "/neuralclear/tasks": {"transaction_id"},
                    "/neuralclear/disputes": {"transaction_id"},
                }
                fields = required.get(request.url.path)
                if not isinstance(body, dict) or fields is not None and set(body) != fields:
                    raise ProtocolError("invalid body")
            except (ProtocolError, UnicodeError):
                return failure("INVALID_REQUEST")
        response = await call_next(request)
        response.headers.update(HEADERS)
        return response

    @app.exception_handler(ProtocolError)
    async def protocol_error(request, exc):
        code = error_code(str(exc))
        return failure(code, 409 if code in {"CONFLICT", "INVALID_STATE_TRANSITION"} else 400)

    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def invalid_body(request, exc):
        return failure("INVALID_REQUEST")

    @app.get("/.well-known/neuralclear/agent.json")
    def discovery():
        return {
            "profile": PROFILE,
            "version": VERSION,
            "currency": ledger.currency,
            "signature_algorithms": ["HMAC-SHA256", "Ed25519"],
            "proof_levels": ["SIGNED_RESULT"],
            "tee_implemented": False,
            "zk_implemented": False,
        }

    @app.post("/neuralclear/quote")
    def prepare(body: dict):
        try:
            workflow.prepare(body["quote"], body["mandate"], body["agent"], body["capability"])
            return ledger.get(body["quote"]["transaction_id"])
        except (KeyError, TypeError):
            raise ProtocolError("invalid request") from None

    @app.post("/neuralclear/tasks")
    def start(body: dict):
        try:
            tx = body["transaction_id"]
            return ledger.start_task(tx)
        except (KeyError, TypeError):
            raise ProtocolError("invalid request") from None

    @app.get("/neuralclear/tasks/{task_id}")
    def task(task_id: str):
        return ledger.get(task_id)

    @app.post("/neuralclear/disputes")
    def dispute(body: dict):
        try:
            return ledger.transition(body["transaction_id"], "DISPUTED")
        except (KeyError, TypeError):
            raise ProtocolError("invalid request") from None

    @app.get("/neuralclear/receipts/{receipt_id}")
    def receipt(receipt_id: str):
        return {
            "receipt": ledger.receipt(
                receipt_id, key=receipt_key, key_id=receipt_key_id, algorithm=algorithm
            ),
            "chain": ledger.chain(receipt_id),
        }

    return app
