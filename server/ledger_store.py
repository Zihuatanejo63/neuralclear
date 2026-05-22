from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from neuralclear import (
    Ledger,
    MockProof,
    Quote,
    ResourceUnit,
    SettlementCredit,
    SpendingMandate,
    TaskResult,
    Transaction,
    TransactionState,
)
from neuralclear.core import ProtocolError

from .models import Receipt, StoredTask
from .registry import build_default_registry


class ReferenceClearingService:
    def __init__(self, platform_fee_bps: int = 1000) -> None:
        self.registry = build_default_registry()
        self.ledger = Ledger()
        self.platform_fee_bps = platform_fee_bps
        self.quotes: dict[str, Quote] = {}
        self.tasks: dict[str, StoredTask] = {}
        self.receipts: dict[str, Receipt] = {}
        self.ledger.open_account("buyer.research", SettlementCredit(1_000, "CC"))
        self.ledger.open_account("agent.pdf_summarizer", SettlementCredit(0, "CC"))

    def request_quote(self, provider: str, capability: str) -> dict[str, object]:
        quote = self.registry.get(provider).quote_for(capability)
        self.quotes[quote.quote_id] = quote
        return quote.to_json()

    def submit_task(
        self,
        task_id: str,
        quote_id: str,
        buyer: str,
        provider: str,
        payload: dict[str, object],
        mandate: SpendingMandate,
    ) -> dict[str, object]:
        quote = self._get_quote(quote_id)
        if quote.provider != provider:
            raise ProtocolError("quote provider mismatch")
        mandate.assert_allows(quote.capability, quote.settlement_price)
        spent_today = self.ledger.get_daily_spend(mandate.agent, mandate.owner, datetime.now(timezone.utc).date())
        mandate.assert_daily_budget(spent_today, quote.settlement_price)

        summary = self._summarize_pdf_text(str(payload.get("text", "")))
        transaction = Transaction(
            sender=buyer,
            receiver=provider,
            amount=quote.settlement_price,
            fee=self._platform_fee(quote.settlement_price),
            capability=quote.capability,
            quote_id=quote.quote_id,
            authorized_agent=mandate.agent,
            state=TransactionState.QUOTE_ACCEPTED,
        )
        transaction.transition(TransactionState.TASK_SUBMITTED)
        transaction.transition(TransactionState.TASK_RUNNING)
        result = TaskResult(
            transaction_id=transaction.transaction_id,
            output={"summary": summary},
            resource_usage=[ResourceUnit(1, "request")],
            settlement_amount=quote.settlement_price,
            proof=MockProof(statement=f"mock proof for task {task_id}"),
        )
        transaction.transition(TransactionState.RESULT_DELIVERED)
        if not result.proof.verify():
            raise ProtocolError("proof verification failed")
        transaction.transition(TransactionState.PROOF_VERIFIED)
        self.ledger.settle(transaction)

        receipt = Receipt(
            receipt_id=f"rcpt_{uuid4().hex}",
            transaction_id=transaction.transaction_id,
            quote_id=quote.quote_id,
            sender=transaction.sender,
            receiver=transaction.receiver,
            amount=transaction.amount.to_json(),
            fee=transaction.fee.to_json(),
            state=transaction.state.value,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.receipts[receipt.receipt_id] = receipt
        task = StoredTask(
            task_id=task_id,
            quote_id=quote_id,
            state=TransactionState.SETTLED.value,
            result={**result.to_json(), "receipt": receipt.to_json()},
        )
        self.tasks[task_id] = task
        return task.to_json()

    def get_task(self, task_id: str) -> dict[str, object]:
        try:
            return self.tasks[task_id].to_json()
        except KeyError as exc:
            raise ProtocolError(f"unknown task: {task_id}") from exc

    def get_receipt(self, receipt_id: str) -> dict[str, object]:
        try:
            return self.receipts[receipt_id].to_json()
        except KeyError as exc:
            raise ProtocolError(f"unknown receipt: {receipt_id}") from exc

    def get_receipt_for_transaction(self, transaction_id: str) -> dict[str, object]:
        for receipt in self.receipts.values():
            if receipt.transaction_id == transaction_id:
                return receipt.to_json()
        raise ProtocolError(f"unknown settlement transaction: {transaction_id}")

    def open_dispute(self, transaction_id: str, opened_by: str, reason: str) -> dict[str, str]:
        return {
            "dispute_id": f"disp_{uuid4().hex}",
            "transaction_id": transaction_id,
            "opened_by": opened_by,
            "reason": reason,
            "state": TransactionState.DISPUTED.value,
        }

    def balances_snapshot(self) -> dict[str, object]:
        return self.ledger.snapshot()

    def _get_quote(self, quote_id: str) -> Quote:
        try:
            return self.quotes[quote_id]
        except KeyError as exc:
            raise ProtocolError(f"unknown quote: {quote_id}") from exc

    def _platform_fee(self, amount: SettlementCredit) -> SettlementCredit:
        fee = max(1, amount.amount * self.platform_fee_bps // 10_000)
        return SettlementCredit(fee, amount.currency)

    @staticmethod
    def _summarize_pdf_text(text: str) -> str:
        cleaned = " ".join(text.split())
        if not cleaned:
            return "No PDF text supplied."
        return cleaned[:220] + ("..." if len(cleaned) > 220 else "")
