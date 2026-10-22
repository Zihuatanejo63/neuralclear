from __future__ import annotations

from datetime import datetime, timezone

from .core import (
    AgentRegistry,
    Ledger,
    MockProof,
    ProtocolError,
    Quote,
    ResourceUnit,
    SpendingMandate,
    TaskResult,
    Transaction,
    TransactionState,
)


class NeuralClearSDK:
    def __init__(self, registry: AgentRegistry, ledger: Ledger, *, profile="legacy") -> None:
        from .wire import PROFILE

        if profile not in {"legacy", PROFILE}:
            raise ProtocolError("unsupported profile")
        self.registry = registry
        self.ledger = ledger
        self.profile = profile

    def escrow(self):
        """Unified opt-in entry; legacy call/request_quote contracts stay unchanged."""
        from .clearing import EscrowWorkflow
        from .escrow import EscrowLedger
        from .wire import PROFILE

        if self.profile != PROFILE or not isinstance(self.ledger, EscrowLedger):
            raise ProtocolError("escrow profile and ledger required")
        return EscrowWorkflow(self.ledger)

    def request_quote(self, provider: str, capability: str, ttl_seconds: int = 300) -> Quote:
        return self.registry.get(provider).quote_for(capability, ttl_seconds=ttl_seconds)

    def call(
        self,
        sender: str,
        provider: str,
        quote: Quote,
        task_payload: object,
        mandate: SpendingMandate | None = None,
    ) -> TaskResult:
        if self.profile != "legacy":
            raise ProtocolError("use sdk.escrow() for explicit escrow execution")
        if quote.is_expired():
            raise ProtocolError("quote expired")
        if provider != quote.provider:
            raise ProtocolError("quote provider mismatch")
        if mandate is not None:
            mandate.assert_allows(quote.capability, quote.settlement_price)
            spent_today = self.ledger.get_daily_spend(
                mandate.agent,
                mandate.owner,
                datetime.now(timezone.utc).date(),
            )
            mandate.assert_daily_budget(spent_today, quote.settlement_price)

        transaction = Transaction(
            sender=sender,
            receiver=provider,
            amount=quote.settlement_price,
            capability=quote.capability,
            quote_id=quote.quote_id,
            authorized_agent=mandate.agent if mandate else sender,
            state=TransactionState.QUOTE_ACCEPTED,
        )
        transaction.transition(TransactionState.TASK_SUBMITTED)
        transaction.transition(TransactionState.TASK_RUNNING)

        result = TaskResult(
            transaction_id=transaction.transaction_id,
            output={"echo": task_payload, "handled_by": provider},
            resource_usage=[
                ResourceUnit(quote.resource_estimate.amount, quote.resource_estimate.unit)
            ],
            settlement_amount=quote.settlement_price,
            proof=MockProof(),
        )

        transaction.transition(TransactionState.RESULT_DELIVERED)
        if not result.proof.verify():
            raise ProtocolError("proof verification failed")
        transaction.transition(TransactionState.PROOF_VERIFIED)
        self.ledger.settle(transaction)
        return result
