"""Design-only port. No USDC custody, RPC, token transfer or finality implementation."""

from typing import Protocol


class StablecoinChannel(Protocol):
    """Implementations must pin chain ID, contract, decimals and licensed partner.

    Deposit evidence needs transaction/log identity and reorg/finality policy.
    Withdrawals need durable idempotency, sanctions controls and reconciliation.
    No claim of legal escrow follows from an on-chain token transfer.
    """

    def deposit_status(self, chain_id: str, transaction_hash: str, log_index: int) -> dict: ...

    def withdraw(self, settlement_id: str, *, idempotency_key: str) -> dict: ...
