"""Clearing gateway: the hosted product surface, stdlib only.

`ClearingGateway` exposes protocol-credit clearing and netting over HTTP.
Balances are clearing credits (`CC`), not customer funds. It refuses a
`neuralclear.escrow` ledger or a `StripeChannel`. Fiat settlement is not live.
Fiat attachment, if added later, is `server.escrow_api` plus
`neuralclear.escrow_channel`. See `docs/ledger-boundary.md`.

Production runs a `TenantHub`: each API key selects that tenant's ledger.
A single optional API key remains for local tests. When no key and no hub
are configured, writes stay open, which is not a production configuration.

    GET  /health/live
    GET  /health/ready
    GET  /health
    GET  /metrics
    POST /v1/accounts                 {account, deposit}
    POST /v1/clear                    {buyer_owner, buyer_agent, provider_url,
                                       capability, payload}
    POST /v1/channels                 {buyer, provider, deposit}
    POST /v1/channels/{id}/meter      {capability, amount, payload_hash}
    POST /v1/channels/{id}/settle
    POST /v1/disputes                 {transaction_id, raised_by, reason}
    POST /v1/disputes/{id}/resolve    {resolution, resolved_by, provider_amount?}
    GET  /v1/ledger
    GET  /v1/receipts/{id}

The recommended deployment terminates TLS in front of this HTTP server.
Direct TLS is optional when certificate paths are supplied.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import signal
import ssl
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Mapping
from urllib.parse import urlsplit

from .accesslog import configure_access_log
from .clearing import ClearingService
from .core import ProtocolError, SettlementCredit
from .httpwire import RemoteProvider
from .metrics import GatewayMetrics
from .netting import NettingService
from .runtime_config import GatewaySettings, GatewayStartupError, load_settings, secret_problem
from .store import ClearingStore
from .tenancy import Tenant, TenantHub

_MAX_BODY = 1_048_576
_PUBLIC_ROUTES = {"/health", "/health/live", "/health/ready", "/metrics"}
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

_GET_ROUTES = (
    (re.compile(r"^/health/live$"), "/health/live"),
    (re.compile(r"^/health/ready$"), "/health/ready"),
    (re.compile(r"^/health$"), "/health"),
    (re.compile(r"^/metrics$"), "/metrics"),
    (re.compile(r"^/v1/ledger$"), "/v1/ledger"),
    (re.compile(r"^/v1/receipts/[\w\-]+$"), "/v1/receipts/{id}"),
)
_POST_ROUTES = (
    (re.compile(r"^/v1/accounts$"), "/v1/accounts"),
    (re.compile(r"^/v1/clear$"), "/v1/clear"),
    (re.compile(r"^/v1/channels$"), "/v1/channels"),
    (re.compile(r"^/v1/channels/[\w\-]+/meter$"), "/v1/channels/{id}/meter"),
    (re.compile(r"^/v1/channels/[\w\-]+/settle$"), "/v1/channels/{id}/settle"),
    (re.compile(r"^/v1/disputes$"), "/v1/disputes"),
    (re.compile(r"^/v1/disputes/[\w\-]+/resolve$"), "/v1/disputes/{id}/resolve"),
)


class _BadRequest(Exception):
    pass


class _BodyTooLarge(Exception):
    pass


@dataclass
class _AuthFailure:
    reason: str


@dataclass
class _AuthOk:
    tenant: Tenant | None


def classify(method: str, path: str) -> str:
    routes = _GET_ROUTES if method == "GET" else _POST_ROUTES if method == "POST" else ()
    for pattern, name in routes:
        if pattern.fullmatch(path):
            return name
    return "other"


class _GatewayServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class ClearingGateway:
    def __init__(
        self,
        clearing: ClearingService | None = None,
        store: ClearingStore | None = None,
        api_key: str | None = None,
        host: str = "127.0.0.1",
        port: int = 0,
        hub: TenantHub | None = None,
        production: bool = False,
        tls_certfile: str | None = None,
        tls_keyfile: str | None = None,
    ) -> None:
        if clearing is not None:
            from .escrow import EscrowLedger as FiatLedger
            from .stripe_channel import StripeChannel

            if isinstance(clearing, (FiatLedger, StripeChannel)):
                raise ProtocolError(
                    "ClearingGateway is the CC sandbox and cannot attach the fiat "
                    "escrow ledger or Stripe channel"
                )
        if hub is not None and store is not None:
            raise GatewayStartupError("pass either a TenantHub or a ClearingStore, not both")
        if hub is not None and api_key is not None:
            raise GatewayStartupError("the single api_key argument cannot be combined with TenantHub")
        if production:
            if hub is None or hub.store is None:
                raise GatewayStartupError("production mode requires a persisted TenantHub")
            if secret_problem(hub.receipt_secret, min_length=32):
                raise GatewayStartupError(
                    "production receipt signing secret is missing or still a placeholder"
                )
            if hub.tenant_count() < 1:
                raise GatewayStartupError("production mode requires at least one tenant API key")
        self.clearing = clearing or ClearingService()
        self.netting = NettingService(self.clearing)
        self.store = store
        self.api_key = api_key
        self.hub = hub
        self.production = production
        self.metrics = GatewayMetrics()
        self.scheme = "http"
        self._providers: dict[str, RemoteProvider] = {}
        self._locks_guard = threading.Lock()
        self._tenant_locks: dict[str, threading.Lock] = {}
        self._log = configure_access_log()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt: str, *args: object) -> None:
                return

            def setup(self) -> None:
                super().setup()
                self.timeout = 30

            def _send(self, status: int, body: dict[str, object]) -> None:
                data = json.dumps(body, default=str).encode("utf-8")
                self._send_bytes(status, data, "application/json")

            def _send_bytes(self, status: int, data: bytes, content_type: str) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                if self.close_connection:
                    self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(data)

            def _request_id(self) -> str:
                supplied = self.headers.get("X-Request-Id", "")
                if _REQUEST_ID.fullmatch(supplied):
                    return supplied
                return uuid.uuid4().hex

            def _read_body(self) -> bytes:
                if self.headers.get("Transfer-Encoding"):
                    self.close_connection = True
                    raise _BadRequest("content length required")
                raw_length = self.headers.get("Content-Length", "0")
                try:
                    length = int(raw_length)
                except ValueError as exc:
                    raise _BadRequest("invalid content length") from exc
                if length < 0:
                    raise _BadRequest("invalid content length")
                if length > _MAX_BODY:
                    self.close_connection = True
                    raise _BodyTooLarge()
                if length == 0:
                    return b""
                data = self.rfile.read(length)
                if len(data) != length:
                    raise _BadRequest("truncated body")
                return data

            def _finish(
                self,
                *,
                method: str,
                path: str,
                route: str,
                status: int,
                tenant_id: str,
                started: float,
                request_id: str,
            ) -> None:
                elapsed = time.perf_counter() - started
                outer.metrics.observe(method, route, status, tenant_id, elapsed)
                outer._log.info(
                    "request",
                    extra={
                        "fields": {
                            "method": method,
                            "path": path,
                            "route": route,
                            "status": status,
                            "duration_ms": round(elapsed * 1000, 3),
                            "tenant_id": tenant_id,
                            "request_id": request_id,
                        }
                    },
                )

            def do_GET(self) -> None:  # noqa: N802
                self._handle("GET")

            def do_POST(self) -> None:  # noqa: N802
                self._handle("POST")

            def _handle(self, method: str) -> None:
                started = time.perf_counter()
                request_id = self._request_id()
                path = urlsplit(self.path).path
                route = classify(method, path)
                status = 500
                tenant_id = "none"
                try:
                    status, tenant_id = self._dispatch(method, path, route)
                except Exception:
                    status = 500
                    if not getattr(self, "_responded", False):
                        detail = "internal error"
                        self._responded = True
                        self._send(500, {"error": detail})
                    outer._log.info(
                        "request failed",
                        extra={"fields": {"request_id": request_id, "route": route}},
                    )
                finally:
                    self._finish(
                        method=method,
                        path=path,
                        route=route,
                        status=status,
                        tenant_id=tenant_id,
                        started=started,
                        request_id=request_id,
                    )

            def _dispatch(self, method: str, path: str, route: str) -> tuple[int, str]:
                self._responded = False
                if method == "GET" and route in _PUBLIC_ROUTES:
                    status = outer._serve_public(self, route)
                    self._responded = True
                    return status, "none"
                if method == "POST":
                    try:
                        raw = self._read_body()
                    except _BodyTooLarge:
                        self._send(413, {"error": "request body too large"})
                        self._responded = True
                        return 413, "anonymous"
                    except _BadRequest as exc:
                        self._send(400, {"error": str(exc)})
                        self._responded = True
                        return 400, "anonymous"
                else:
                    raw = b""
                if outer.hub is None and method == "GET":
                    auth: _AuthOk | _AuthFailure = _AuthOk(None)
                else:
                    provided = self.headers.get("X-NeuralClear-Api-Key", "")
                    auth = outer.authenticate(provided)
                if isinstance(auth, _AuthFailure):
                    outer.metrics.auth_failure(auth.reason)
                    self._send(401, {"error": "invalid api key"})
                    self._responded = True
                    return 401, "anonymous"
                tenant_id = "legacy" if auth.tenant is None else auth.tenant.tenant_id
                try:
                    if method == "GET":
                        status, body = outer._route_get_locked(path, auth.tenant)
                        self._send(status, body)
                        self._responded = True
                        return status, tenant_id
                    body_obj = json.loads(raw.decode("utf-8")) if raw else {}
                    if not isinstance(body_obj, dict):
                        self._send(400, {"error": "invalid json"})
                        self._responded = True
                        return 400, tenant_id
                    result = outer._route_post(path, body_obj, auth.tenant)
                    self._send(200, result)
                    self._responded = True
                    return 200, tenant_id
                except json.JSONDecodeError:
                    self._send(400, {"error": "invalid json"})
                    self._responded = True
                    return 400, tenant_id
                except ProtocolError as exc:
                    self._send(400, {"error": str(exc)})
                    self._responded = True
                    return 400, tenant_id
                except KeyError as exc:
                    self._send(400, {"error": f"missing field: {exc}"})
                    self._responded = True
                    return 400, tenant_id
                except Exception as exc:
                    detail = "internal error" if outer.production else str(exc)
                    self._send(500, {"error": detail})
                    self._responded = True
                    outer._log.info(
                        "handler error",
                        extra={"fields": {"route": route, "error_type": type(exc).__name__}},
                    )
                    return 500, tenant_id

        self._server = _GatewayServer((host, port), Handler)
        if tls_certfile or tls_keyfile:
            if not tls_certfile or not tls_keyfile:
                raise GatewayStartupError("direct TLS requires both a certificate and a key path")
            self._enable_tls(tls_certfile, tls_keyfile)
        self._thread: threading.Thread | None = None

    def authenticate(self, provided: str) -> _AuthOk | _AuthFailure:
        if self.hub is not None:
            if not provided:
                return _AuthFailure("missing")
            try:
                return _AuthOk(self.hub.by_key(provided))
            except ProtocolError:
                return _AuthFailure("invalid")
        if self.api_key is None:
            return _AuthOk(None)
        if not hmac.compare_digest(provided, self.api_key):
            return _AuthFailure("missing" if not provided else "invalid")
        return _AuthOk(None)

    def _enable_tls(self, certfile: str, keyfile: str) -> None:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        try:
            context.load_cert_chain(certfile, keyfile)
        except (OSError, ssl.SSLError) as exc:
            raise GatewayStartupError("could not load the direct TLS certificate") from exc
        self._server.socket = context.wrap_socket(self._server.socket, server_side=True)
        self.scheme = "https"

    def _serve_public(self, handler: BaseHTTPRequestHandler, route: str) -> int:
        if route == "/health/live":
            handler._send(  # type: ignore[attr-defined]
                200,
                {
                    "status": "ok",
                    "service": "neuralclear-gateway",
                    "fiat_settlement": "not_live",
                },
            )
            return 200
        if route == "/metrics":
            ready, _body = self.readiness()
            payload = self.metrics.render(ready=ready == 200).encode("utf-8")
            handler._send_bytes(  # type: ignore[attr-defined]
                200,
                payload,
                "text/plain; version=0.0.4; charset=utf-8",
            )
            return 200
        status, body = self.readiness()
        handler._send(status, body)  # type: ignore[attr-defined]
        return status

    def readiness(self) -> tuple[int, dict[str, object]]:
        storage = "unconfigured"
        ok = True
        if self.hub is not None and self.hub.store is not None:
            ok = self.hub.store.ping()
            storage = "ok" if ok else "error"
        elif self.store is not None:
            ok = _ping_sqlite(self.store.path)
            storage = "ok" if ok else "error"
        body = {
            "status": "ok" if ok else "unavailable",
            "service": "neuralclear-gateway",
            "storage": storage,
            "fiat_settlement": "not_live",
        }
        return (200 if ok else 503), body

    def _lock_for(self, tenant_id: str) -> threading.Lock:
        with self._locks_guard:
            lock = self._tenant_locks.get(tenant_id)
            if lock is None:
                lock = threading.Lock()
                self._tenant_locks[tenant_id] = lock
            return lock

    def _route_get(self, path: str, clearing: ClearingService) -> tuple[int, dict[str, object]]:
        if path == "/v1/ledger":
            snapshot = clearing.ledger.snapshot()
            return 200, snapshot
        match = re.fullmatch(r"/v1/receipts/([\w\-]+)", path)
        if match:
            receipt = clearing.receipts.get(match.group(1))
            if receipt is None:
                return 404, {"error": "receipt not found"}
            return 200, receipt
        return 404, {"error": "not found"}

    def _route_post(
        self,
        path: str,
        body: dict[str, object],
        tenant: Tenant | None,
    ) -> dict[str, object]:
        if tenant is None:
            return self._route_post_locked(path, body, self.clearing, self.netting, None)
        with self._lock_for(tenant.tenant_id):
            netting = tenant.netting or NettingService(tenant.clearing)
            tenant.netting = netting
            return self._route_post_locked(path, body, tenant.clearing, netting, tenant)

    def _route_get_locked(self, path: str, tenant: Tenant | None) -> tuple[int, dict[str, object]]:
        clearing = _clearing_of(self, tenant)
        if tenant is None:
            return self._route_get(path, clearing)
        with self._lock_for(tenant.tenant_id):
            return self._route_get(path, clearing)

    def _route_post_locked(
        self,
        path: str,
        body: dict[str, object],
        clearing: ClearingService,
        netting: NettingService,
        tenant: Tenant | None,
    ) -> dict[str, object]:
        if path == "/v1/accounts":
            account = str(body["account"])
            deposit = int(body.get("deposit", 0))  # type: ignore[arg-type]
            clearing.ledger.open_account(account, SettlementCredit(deposit))
            self._persist(tenant)
            return {"account": account, "balance": deposit}

        if path == "/v1/clear":
            receipt = self._clear(body, clearing)
            self._persist(tenant)
            return receipt

        if path == "/v1/channels":
            channel = netting.open_channel(
                str(body["buyer"]), str(body["provider"]), int(body["deposit"])  # type: ignore[arg-type]
            )
            self._persist(tenant)
            return {"channel_id": channel.channel_id, "spendable": channel.spendable()}

        meter = re.fullmatch(r"/v1/channels/([\w\-]+)/meter", path)
        if meter:
            channel = netting._get(meter.group(1))
            record = channel.meter(
                str(body["capability"]),
                int(body["amount"]),  # type: ignore[arg-type]
                str(body["payload_hash"]),
            )
            self._persist(tenant)
            return record.to_json()

        settle = re.fullmatch(r"/v1/channels/([\w\-]+)/settle", path)
        if settle:
            receipt = netting.settle(settle.group(1))
            self._persist(tenant)
            return receipt

        if path == "/v1/disputes":
            evidence = body.get("evidence")
            dispute = clearing.open_dispute(
                str(body["transaction_id"]),
                str(body["raised_by"]),
                str(body["reason"]),
                evidence if isinstance(evidence, dict) else None,
            )
            self._persist(tenant)
            return dispute.to_json()

        resolve = re.fullmatch(r"/v1/disputes/([\w\-]+)/resolve", path)
        if resolve:
            amount = body.get("provider_amount")
            dispute = clearing.resolve_dispute(
                resolve.group(1),
                str(body["resolution"]),
                str(body["resolved_by"]),
                int(amount) if amount is not None else None,  # type: ignore[arg-type]
            )
            self._persist(tenant)
            return dispute.to_json()

        raise ProtocolError(f"unknown endpoint: {path}")

    def _clear(self, body: dict[str, object], clearing: ClearingService) -> dict[str, object]:
        provider_url = str(body["provider_url"])
        remote = self._providers.get(provider_url)
        if remote is None:
            remote = RemoteProvider(provider_url)
            self._providers[provider_url] = remote
        quote = remote.handle_quote(str(body["capability"]))
        receipt = clearing.clear(
            buyer_owner=str(body["buyer_owner"]),
            buyer_agent=str(body.get("buyer_agent", body["buyer_owner"])),
            quote=quote,
            run=lambda: remote.handle_task(quote, body.get("payload")),
        )
        return receipt

    def _persist(self, tenant: Tenant | None) -> None:
        if tenant is not None and self.hub is not None:
            self.hub.persist(tenant)
            return
        if self.store is not None:
            self.store.save(self.clearing)

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        if isinstance(host, bytes):
            host = host.decode("utf-8")
        return f"{self.scheme}://{host}:{port}"

    def start(self) -> "ClearingGateway":
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._thread is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
        self._thread = None


def _clearing_of(gateway: ClearingGateway, tenant: Tenant | None) -> ClearingService:
    if tenant is None:
        return gateway.clearing
    return tenant.clearing


def _ping_sqlite(path: str) -> bool:
    import sqlite3

    try:
        connection = sqlite3.connect(path)
        try:
            connection.execute("SELECT 1")
        finally:
            connection.close()
        return True
    except sqlite3.Error:
        return False


def assemble_gateway(settings: GatewaySettings) -> ClearingGateway:
    hub = TenantHub(store_path=settings.db_path, receipt_secret=settings.receipt_secret)
    if settings.bootstrap_api_key:
        hub.ensure_bootstrap(settings.bootstrap_tenant_name, settings.bootstrap_api_key)
    return ClearingGateway(
        hub=hub,
        host=settings.host,
        port=settings.port,
        production=settings.production,
        tls_certfile=settings.tls_certfile,
        tls_keyfile=settings.tls_keyfile,
    )


def serve(settings: GatewaySettings) -> None:
    if not settings.production:
        print(
            "NEURALCLEAR_ENV=development: this process is not the production deployment "
            "and fiat settlement is not live.",
            file=sys.stderr,
        )
    gateway = assemble_gateway(settings)
    gateway.start()
    host, port = gateway._server.server_address[:2]
    gateway._log.info(
        "listening",
        extra={
            "fields": {
                "host": host.decode("utf-8") if isinstance(host, bytes) else host,
                "port": port,
                "tls_mode": settings.tls_mode,
                "production": settings.production,
                "fiat_settlement": "not_live",
                "tenants": gateway.hub.tenant_count() if gateway.hub is not None else 0,
            }
        },
    )
    stopped = threading.Event()

    def _stop(signum: int, _frame: object) -> None:
        gateway._log.info("stopping", extra={"fields": {"signal": signum}})
        stopped.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    try:
        while not stopped.wait(3600):
            continue
    finally:
        gateway.stop()


def _open_hub(settings: GatewaySettings) -> TenantHub:
    return TenantHub(store_path=settings.db_path, receipt_secret=settings.receipt_secret)


def main(argv: list[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="neuralclear.gateway")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve", help="run the clearing gateway")
    create = sub.add_parser("tenant-create", help="issue a tenant API key")
    create.add_argument("--name", required=True)
    rotate = sub.add_parser("tenant-rotate", help="rotate a tenant API key")
    rotate.add_argument("--tenant-id", required=True)
    args = parser.parse_args(argv)
    env = environ if environ is not None else os.environ
    try:
        settings = load_settings(env, command=str(args.command))
        if args.command == "serve":
            serve(settings)
            return 0
        if args.command == "tenant-create":
            return _tenant_create(settings, str(args.name))
        return _tenant_rotate(settings, str(args.tenant_id))
    except GatewayStartupError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _tenant_create(settings: GatewaySettings, name: str) -> int:
    hub = _open_hub(settings)
    try:
        tenant = hub.create_tenant(name)
    except ProtocolError:
        print("could not create tenant", file=sys.stderr)
        return 1
    print(f"tenant_id={tenant.tenant_id}")
    print(f"api_key={tenant.api_key}")
    print(
        "Store this API key now. It is not saved in plaintext and will not be shown again.",
        file=sys.stderr,
    )
    return 0


def _tenant_rotate(settings: GatewaySettings, tenant_id: str) -> int:
    hub = _open_hub(settings)
    try:
        new_key = hub.rotate_key(tenant_id)
    except ProtocolError:
        print("could not rotate tenant key", file=sys.stderr)
        return 1
    print(f"tenant_id={tenant_id}")
    print(f"api_key={new_key}")
    print("The previous API key no longer authenticates.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
