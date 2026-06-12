"""HTTP wire layer: real cross-process agent transactions, stdlib only.

Turns any `ProviderAgent` into a standalone HTTP service and gives buyers a
`RemoteProvider` client with the same interface as a local provider — so the
clearing flow runs over real network boundaries with zero third-party
dependencies (no FastAPI, no requests; `http.server` + `urllib`).

Provider endpoints:

    GET  /.well-known/neuralclear/agent.json   manifest
    POST /neuralclear/quote     {"capability": "..."}            -> Quote
    POST /neuralclear/task      {"quote": {...}, "payload": ...} -> TaskResult

`RemoteProvider` mirrors `ProviderAgent.handle_quote/handle_task/agent_info`,
so `BuyerAgent.connect_remote(url)` is a drop-in replacement for
`connect_local(provider)`.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .core import (
    AgentInfo,
    Capability,
    MockProof,
    ProtocolError,
    Quote,
    ResourceUnit,
    SettlementCredit,
    TaskResult,
)
from .provider import ProviderAgent

# ---------------------------------------------------------------------------
# Wire serialization
# ---------------------------------------------------------------------------


def quote_to_wire(quote: Quote) -> dict[str, object]:
    return {
        "quote_id": quote.quote_id,
        "provider": quote.provider,
        "capability": quote.capability,
        "resource_estimate": quote.resource_estimate.to_json(),
        "settlement_price": quote.settlement_price.to_json(),
        "expires_at": quote.expires_at,
    }


def quote_from_wire(data: dict[str, object]) -> Quote:
    try:
        resource = data["resource_estimate"]
        price = data["settlement_price"]
        return Quote(
            provider=str(data["provider"]),
            capability=str(data["capability"]),
            resource_estimate=ResourceUnit(
                float(resource["amount"]), str(resource["unit"])  # type: ignore[index]
            ),
            settlement_price=SettlementCredit(
                int(price["amount"]), str(price["currency"])  # type: ignore[index]
            ),
            expires_at=float(data["expires_at"]),  # type: ignore[arg-type]
            quote_id=str(data["quote_id"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProtocolError(f"malformed quote on wire: {exc}") from exc


def result_to_wire(result: TaskResult) -> dict[str, object]:
    return result.to_json()


def result_from_wire(data: dict[str, object]) -> TaskResult:
    try:
        usage = [
            ResourceUnit(float(item["amount"]), str(item["unit"]))  # type: ignore[index]
            for item in data.get("resource_usage", [])  # type: ignore[union-attr]
        ]
        amount = data["settlement_amount"]
        return TaskResult(
            transaction_id=str(data.get("transaction_id", "")),
            output=data.get("output"),
            resource_usage=usage,
            settlement_amount=SettlementCredit(
                int(amount["amount"]), str(amount["currency"])  # type: ignore[index]
            ),
            proof=MockProof(),  # wire carries proof metadata; verification is local policy
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProtocolError(f"malformed task result on wire: {exc}") from exc


def agent_info_from_manifest(data: dict[str, object]) -> AgentInfo:
    capabilities = []
    for item in data.get("capabilities", []):  # type: ignore[union-attr]
        capabilities.append(
            Capability(
                name=str(item["name"]),  # type: ignore[index]
                resource_price=ResourceUnit(
                    float(item["resource_price"]["amount"]),  # type: ignore[index]
                    str(item["resource_price"]["unit"]),  # type: ignore[index]
                ),
                settlement_price=SettlementCredit(
                    int(item["settlement_price"]["amount"]),  # type: ignore[index]
                    str(item["settlement_price"]["currency"]),  # type: ignore[index]
                ),
                description=str(item.get("description", "")),  # type: ignore[union-attr]
            )
        )
    return AgentInfo(
        agent_id=str(data["agent_id"]),
        name=str(data.get("name", data["agent_id"])),
        endpoint=str(data.get("endpoint", "")),
        public_key=str(data.get("public_key", "")),
        capabilities=capabilities,
        reputation_score=float(data.get("reputation_score", 0.0)),  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Provider HTTP server
# ---------------------------------------------------------------------------


class ProviderHTTPServer:
    """Serves a ProviderAgent over HTTP. `start()` runs in a daemon thread."""

    def __init__(self, provider: ProviderAgent, host: str = "127.0.0.1", port: int = 0) -> None:
        self.provider = provider
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: object) -> None:  # silence
                pass

            def _send(self, status: int, body: dict[str, object]) -> None:
                data = json.dumps(body).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _read_json(self) -> dict[str, object]:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0:
                    return {}
                return json.loads(self.rfile.read(length).decode("utf-8"))

            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/.well-known/neuralclear/agent.json":
                    self._send(200, outer.provider.manifest())
                else:
                    self._send(404, {"error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                try:
                    body = self._read_json()
                    if self.path == "/neuralclear/quote":
                        quote = outer.provider.handle_quote(str(body.get("capability", "")))
                        self._send(200, quote_to_wire(quote))
                    elif self.path == "/neuralclear/task":
                        quote = quote_from_wire(body["quote"])  # type: ignore[arg-type]
                        result = outer.provider.handle_task(quote, body.get("payload"))
                        self._send(200, result_to_wire(result))
                    else:
                        self._send(404, {"error": "not found"})
                except ProtocolError as exc:
                    self._send(400, {"error": str(exc)})
                except Exception as exc:  # pragma: no cover - defensive
                    self._send(500, {"error": str(exc)})

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def start(self) -> "ProviderHTTPServer":
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()


# ---------------------------------------------------------------------------
# Remote provider client (buyer side)
# ---------------------------------------------------------------------------


class RemoteProvider:
    """HTTP client mirroring the ProviderAgent interface (duck-typed)."""

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._info = agent_info_from_manifest(
            self._get("/.well-known/neuralclear/agent.json")
        )
        self.agent_id = self._info.agent_id

    # ProviderAgent-compatible surface ---------------------------------
    def agent_info(self) -> AgentInfo:
        return self._info

    def handle_quote(self, capability: str, ttl_seconds: int = 300) -> Quote:
        data = self._post("/neuralclear/quote", {"capability": capability})
        return quote_from_wire(data)

    def handle_task(self, quote: Quote, payload: object) -> TaskResult:
        data = self._post(
            "/neuralclear/task",
            {"quote": quote_to_wire(quote), "payload": payload},
        )
        return result_from_wire(data)

    # HTTP internals -----------------------------------------------------
    def _get(self, path: str) -> dict[str, object]:
        return self._request(urllib.request.Request(self.base_url + path))

    def _post(self, path: str, body: dict[str, object]) -> dict[str, object]:
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return self._request(request)

    def _request(self, request: urllib.request.Request) -> dict[str, object]:
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("error", str(exc))
            except Exception:  # pragma: no cover
                detail = str(exc)
            raise ProtocolError(f"provider error: {detail}") from exc
        except urllib.error.URLError as exc:
            raise ProtocolError(f"provider unreachable: {exc.reason}") from exc
