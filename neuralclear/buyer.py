"""Buyer SDK: one call from capability name to settled receipt.

    from neuralclear.buyer import BuyerAgent

    buyer = BuyerAgent("buyer.research", registry=registry, ledger=ledger, mandate=mandate)
    outcome = buyer.purchase("summarize.pdf", payload={"text": "..."})

    outcome.result    # TaskResult from the provider
    outcome.receipt   # settlement record for apps, billing, analytics

The buyer runs the full clearing flow: discover -> quote -> mandate check ->
task submit -> proof verify -> settle, and raises ProtocolError at the first
violated rule so products can enforce budgets and approvals.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .core import (
    AgentRegistry,
    Ledger,
    ProtocolError,
    Quote,
    SpendingMandate,
    TaskResult,
    Transaction,
    TransactionState,
)
from .provider import ProviderAgent


@dataclass(frozen=True)
class PurchaseOutcome:
    """Everything a product needs after a completed agent-to-agent purchase."""

    result: TaskResult
    transaction: Transaction
    receipt: dict[str, object]


class BuyerAgent:
    def __init__(
        self,
        agent_id: str,
        registry: AgentRegistry,
        ledger: Ledger,
        mandate: SpendingMandate | None = None,
        owner: str | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.registry = registry
        self.ledger = ledger
        self.mandate = mandate
        self.owner = owner or agent_id
        # Optional direct handle to in-process providers (sandbox mode).
        self._local_providers: dict[str, ProviderAgent] = {}

    # ------------------------------------------------------------------
    # Sandbox wiring
    # ------------------------------------------------------------------
    def connect_local(self, provider: ProviderAgent) -> None:
        """Register an in-process provider for sandbox/demo execution."""
        self._local_providers[provider.agent_id] = provider
        try:
            self.registry.register(provider.agent_info())
        except ProtocolError:
            pass  # already registered

    def connect_remote(self, base_url: str) -> str:
        """Register a provider served over HTTP (its /.well-known manifest is
        fetched and entered into the registry). Returns the agent_id."""
        from .httpwire import RemoteProvider  # local import: keeps core import-light

        remote = RemoteProvider(base_url)
        self._local_providers[remote.agent_id] = remote  # duck-typed interface
        try:
            self.registry.register(remote.agent_info())
        except ProtocolError:
            pass
        return remote.agent_id

    # ------------------------------------------------------------------
    # Flow steps (usable individually)
    # ------------------------------------------------------------------
    def discover(self, capability: str) -> list[str]:
        return [agent.agent_id for agent in self.registry.discover(capability)]

    def request_quote(self, provider_id: str, capability: str, ttl_seconds: int = 300) -> Quote:
        local = self._local_providers.get(provider_id)
        if local is not None:
            return local.handle_quote(capability, ttl_seconds=ttl_seconds)
        return self.registry.get(provider_id).quote_for(capability, ttl_seconds=ttl_seconds)

    def authorize(self, quote: Quote) -> None:
        """Mandate and budget checks. Raises ProtocolError when not allowed."""
        if self.mandate is None:
            return
        self.mandate.assert_allows(quote.capability, quote.settlement_price)
        spent_today = self.ledger.get_daily_spend(
            self.mandate.agent,
            self.mandate.owner,
            datetime.now(timezone.utc).date(),
        )
        self.mandate.assert_daily_budget(spent_today, quote.settlement_price)

    # ------------------------------------------------------------------
    # One-call flow
    # ------------------------------------------------------------------
    def purchase(
        self,
        capability: str,
        payload: object,
        provider_id: str | None = None,
        ttl_seconds: int = 300,
    ) -> PurchaseOutcome:
        if provider_id is None:
            candidates = self.discover(capability)
            if not candidates:
                raise ProtocolError(f"no provider found for capability: {capability}")
            provider_id = candidates[0]

        quote = self.request_quote(provider_id, capability, ttl_seconds=ttl_seconds)
        if quote.is_expired():
            raise ProtocolError("quote expired")
        self.authorize(quote)

        transaction = Transaction(
            sender=self.owner,
            receiver=provider_id,
            amount=quote.settlement_price,
            capability=quote.capability,
            quote_id=quote.quote_id,
            authorized_agent=self.mandate.agent if self.mandate else self.agent_id,
            state=TransactionState.QUOTE_ACCEPTED,
        )
        transaction.transition(TransactionState.TASK_SUBMITTED)
        transaction.transition(TransactionState.TASK_RUNNING)

        result = self._execute(provider_id, quote, payload, transaction.transaction_id)

        transaction.transition(TransactionState.RESULT_DELIVERED)
        if not result.proof.verify():
            raise ProtocolError("proof verification failed")
        transaction.transition(TransactionState.PROOF_VERIFIED)
        self.ledger.settle(transaction)

        return PurchaseOutcome(
            result=result,
            transaction=transaction,
            receipt=self._receipt(transaction, result),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _execute(
        self,
        provider_id: str,
        quote: Quote,
        payload: object,
        transaction_id: str,
    ) -> TaskResult:
        local = self._local_providers.get(provider_id)
        if local is None:
            raise ProtocolError(
                "no execution channel for provider; "
                "use connect_local() in sandbox mode or the HTTP client for remote providers"
            )
        result = local.handle_task(quote, payload)
        return TaskResult(
            transaction_id=transaction_id,
            output=result.output,
            resource_usage=result.resource_usage,
            settlement_amount=result.settlement_amount,
            proof=result.proof,
        )

    @staticmethod
    def _receipt(transaction: Transaction, result: TaskResult) -> dict[str, object]:
        return {
            "receipt_id": f"rcpt_{transaction.transaction_id}",
            "transaction": transaction.to_json(),
            "resource_usage": [item.to_json() for item in result.resource_usage],
            "proof": result.proof.to_json(),
            "issued_at": transaction.settled_at.isoformat() if transaction.settled_at else None,
        }
