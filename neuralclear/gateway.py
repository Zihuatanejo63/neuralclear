"""Clearing gateway: the hosted product surface, stdlib only.

`ClearingGateway` exposes a `ClearingService` + `NettingService` over HTTP.
This is the V0.4 shape: buyers and providers anywhere on the network, one
neutral clearing point that holds escrow, meters channels, signs receipts,
and persists to SQLite. API-key write protection included.

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

The gateway executes provider tasks itself over HTTP (`RemoteProvider`), so
a single `/v1/clear` call runs the entire loop: quote -> mandate -> hold ->
remote execution -> proof -> release -> signed receipt.
"""

from __future__ import annotations

import hmac
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .clearing import ClearingService
from .core import ProtocolError, SettlementCredit
from .httpwire import RemoteProvider
from .netting import NettingService
from .store import ClearingStore


class ClearingGateway:
    def __init__(
        self,
        clearing: ClearingService | None = None,
        store: ClearingStore | None = None,
        api_key: str | None = None,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        self.clearing = clearing or ClearingService()
        self.netting = NettingService(self.clearing)
        self.store = store
        self.api_key = api_key
        self._providers: dict[str, RemoteProvider] = {}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: object) -> None:
                pass

            def _send(self, status: int, body: dict[str, object]) -> None:
                data = json.dumps(body, default=str).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _body(self) -> dict[str, object]:
                length = int(self.headers.get("Content-Length", "0"))
                return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

            def _authorized(self) -> bool:
                if outer.api_key is None:
                    return True
                provided = self.headers.get("X-NeuralClear-Api-Key", "")
                return hmac.compare_digest(provided, outer.api_key)

            def do_GET(self) -> None:  # noqa: N802
                try:
                    if self.path == "/v1/ledger":
                        self._send(200, outer.clearing.ledger.snapshot())
                        return
                    match = re.fullmatch(r"/v1/receipts/([\w\-]+)", self.path)
                    if match:
                        receipt = outer.clearing.receipts.get(match.group(1))
                        if receipt is None:
                            self._send(404, {"error": "receipt not found"})
                        else:
                            self._send(200, receipt)
                        return
                    self._send(404, {"error": "not found"})
                except Exception as exc:  # pragma: no cover
                    self._send(500, {"error": str(exc)})

            def do_POST(self) -> None:  # noqa: N802
                if not self._authorized():
                    self._send(401, {"error": "invalid api key"})
                    return
                try:
                    self._send(200, outer._route_post(self.path, self._body()))
                except ProtocolError as exc:
                    self._send(400, {"error": str(exc)})
                except KeyError as exc:
                    self._send(400, {"error": f"missing field: {exc}"})
                except Exception as exc:  # pragma: no cover
                    self._send(500, {"error": str(exc)})

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------
    def _route_post(self, path: str, body: dict[str, object]) -> dict[str, object]:
        if path == "/v1/accounts":
            account = str(body["account"])
            deposit = int(body.get("deposit", 0))
            self.clearing.ledger.open_account(account, SettlementCredit(deposit))
            self._persist()
            return {"account": account, "balance": deposit}

        if path == "/v1/clear":
            return self._clear(body)

        if path == "/v1/channels":
            channel = self.netting.open_channel(
                str(body["buyer"]), str(body["provider"]), int(body["deposit"])
            )
            self._persist()
            return {"channel_id": channel.channel_id, "spendable": channel.spendable()}

        meter = re.fullmatch(r"/v1/channels/([\w\-]+)/meter", path)
        if meter:
            channel = self.netting._get(meter.group(1))
            record = channel.meter(
                str(body["capability"]), int(body["amount"]), str(body["payload_hash"])
            )
            return record.to_json()

        settle = re.fullmatch(r"/v1/channels/([\w\-]+)/settle", path)
        if settle:
            receipt = self.netting.settle(settle.group(1))
            self._persist()
            return receipt

        if path == "/v1/disputes":
            dispute = self.clearing.open_dispute(
                str(body["transaction_id"]),
                str(body["raised_by"]),
                str(body["reason"]),
                body.get("evidence") if isinstance(body.get("evidence"), dict) else None,
            )
            return dispute.to_json()

        resolve = re.fullmatch(r"/v1/disputes/([\w\-]+)/resolve", path)
        if resolve:
            amount = body.get("provider_amount")
            dispute = self.clearing.resolve_dispute(
                resolve.group(1),
                str(body["resolution"]),
                str(body["resolved_by"]),
                int(amount) if amount is not None else None,
            )
            self._persist()
            return dispute.to_json()

        raise ProtocolError(f"unknown endpoint: {path}")

    def _clear(self, body: dict[str, object]) -> dict[str, object]:
        provider_url = str(body["provider_url"])
        remote = self._providers.get(provider_url)
        if remote is None:
            remote = RemoteProvider(provider_url)
            self._providers[provider_url] = remote
        quote = remote.handle_quote(str(body["capability"]))
        receipt = self.clearing.clear(
            buyer_owner=str(body["buyer_owner"]),
            buyer_agent=str(body.get("buyer_agent", body["buyer_owner"])),
            quote=quote,
            run=lambda: remote.handle_task(quote, body.get("payload")),
        )
        self._persist()
        return receipt

    def _persist(self) -> None:
        if self.store is not None:
            self.store.save(self.clearing)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def start(self) -> "ClearingGateway":
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
