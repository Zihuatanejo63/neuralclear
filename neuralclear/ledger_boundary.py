"""Boundary between sandbox credits and commercial fiat.

Commercial fiat uses ``neuralclear.escrow`` and ``neuralclear.escrow_channel``
as the funds source of truth. ``neuralclear.clearing`` holds protocol credits
(``CC``) for semantics and the sandbox only.

Nothing in this tree posts a credit balance into a fiat balance, or a fiat
balance into a credit balance. There is no peg, rate, or 1:1 relabeling.
``convert_credit_to_fiat`` and ``convert_fiat_to_credit`` exist so callers
and tests hit one refusal instead of inventing a bridge.
"""

from __future__ import annotations

import re

CREDIT_CURRENCY = "CC"
FIAT_LEDGER = "neuralclear.escrow"
CREDIT_LEDGER = "neuralclear.clearing"


def _refuse(message: str) -> None:
    from .core import ProtocolError

    raise ProtocolError(message)


def is_credit_currency(currency: object) -> bool:
    return isinstance(currency, str) and currency.upper() == CREDIT_CURRENCY


def require_credit_currency(currency: str) -> str:
    """Accept only the sandbox credit code."""
    if currency != CREDIT_CURRENCY:
        _refuse("clearing credits are CC only; fiat amounts are not credits")
    return currency


def require_fiat_currency(currency: str) -> str:
    """Accept a lowercase ISO code. Protocol credits are not fiat."""
    if (
        not isinstance(currency, str)
        or is_credit_currency(currency)
        or re.fullmatch(r"[a-z]{3}", currency) is None
    ):
        _refuse(
            "fiat currency must be a lowercase ISO code and cannot be protocol credits (CC)"
        )
    return currency


def convert_credit_to_fiat(amount: object, credit_currency: object, fiat_currency: object) -> None:
    _refuse(
        "automatic credit-to-fiat conversion is forbidden "
        f"({credit_currency} -> {fiat_currency})"
    )


def convert_fiat_to_credit(amount: object, fiat_currency: object, credit_currency: object) -> None:
    _refuse(
        "automatic fiat-to-credit conversion is forbidden "
        f"({fiat_currency} -> {credit_currency})"
    )
