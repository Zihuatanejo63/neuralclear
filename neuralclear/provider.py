"""Provider SDK: make any Python function a transaction-ready agent capability.

The goal is a ten-line integration for agent developers:

    from neuralclear.provider import ProviderAgent

    agent = ProviderAgent("agent.pdf_summarizer", endpoint="https://agent.example.com")

    @agent.capability("summarize.pdf", price=25, resource_estimate=8000, resource_unit="tokens")
    def summarize(payload):
        return {"summary": payload["text"][:100]}

The agent now produces a `.well-known` manifest, quotes, executes tasks, and
returns `TaskResult` objects with proof metadata — without the developer
touching protocol internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

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

TaskHandler = Callable[[object], object]


@dataclass
class _RegisteredCapability:
    capability: Capability
    handler: TaskHandler


class ProviderAgent:
    """Wraps capability handlers and exposes protocol surfaces.

    This class intentionally has no HTTP dependency. The reference server (or
    any framework the developer prefers) can mount `manifest()`,
    `handle_quote()`, and `handle_task()` behind routes.
    """

    def __init__(
        self,
        agent_id: str,
        endpoint: str = "",
        public_key: str = "",
        currency: str = "CC",
        name: str = "",
    ) -> None:
        self.agent_id = agent_id
        self.name = name or agent_id
        self.endpoint = endpoint
        self.public_key = public_key
        self.currency = currency
        self._capabilities: dict[str, _RegisteredCapability] = {}
        self._issued_quotes: dict[str, Quote] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def capability(
        self,
        name: str,
        price: int,
        resource_estimate: float = 0,
        resource_unit: str = "tokens",
    ) -> Callable[[TaskHandler], TaskHandler]:
        """Decorator registering a handler as a priced capability."""

        if price <= 0:
            raise ProtocolError("capability price must be positive")

        def decorator(handler: TaskHandler) -> TaskHandler:
            cap = Capability(
                name=name,
                resource_price=ResourceUnit(resource_estimate, resource_unit),
                settlement_price=SettlementCredit(price, self.currency),
            )
            self._capabilities[name] = _RegisteredCapability(cap, handler)
            return handler

        return decorator

    # ------------------------------------------------------------------
    # Protocol surfaces
    # ------------------------------------------------------------------
    def agent_info(self) -> AgentInfo:
        return AgentInfo(
            agent_id=self.agent_id,
            name=self.name,
            endpoint=self.endpoint,
            public_key=self.public_key,
            capabilities=[item.capability for item in self._capabilities.values()],
        )

    def manifest(self) -> dict[str, object]:
        """The `/.well-known/neuralclear/agent.json` document."""
        return self.agent_info().to_json()

    def handle_quote(self, capability: str, ttl_seconds: int = 300) -> Quote:
        if capability not in self._capabilities:
            raise ProtocolError(f"unknown capability: {capability}")
        quote = self.agent_info().quote_for(capability, ttl_seconds=ttl_seconds)
        self._issued_quotes[quote.quote_id] = quote
        return quote

    def handle_task(self, quote: Quote, payload: object) -> TaskResult:
        """Execute work against a previously issued quote."""
        if quote.provider != self.agent_id:
            raise ProtocolError("quote was not issued by this provider")
        if quote.is_expired():
            raise ProtocolError("quote expired")
        registered = self._capabilities.get(quote.capability)
        if registered is None:
            raise ProtocolError(f"unknown capability: {quote.capability}")

        output = registered.handler(payload)

        return TaskResult(
            transaction_id="",  # assigned by the buyer/clearing side
            output=output,
            resource_usage=[
                ResourceUnit(quote.resource_estimate.amount, quote.resource_estimate.unit)
            ],
            settlement_amount=quote.settlement_price,
            proof=MockProof(),
        )

    @property
    def capabilities(self) -> list[str]:
        return list(self._capabilities)
