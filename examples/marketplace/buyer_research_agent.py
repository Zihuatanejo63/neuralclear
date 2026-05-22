from __future__ import annotations

from datetime import datetime, timedelta, timezone

from neuralclear import SettlementCredit, SpendingMandate


def research_buyer_mandate() -> SpendingMandate:
    return SpendingMandate(
        owner="buyer.research",
        agent="buyer.research.agent",
        allowed_capabilities=["summarize.pdf"],
        max_per_task=SettlementCredit(100, "CC"),
        max_daily=SettlementCredit(1_000, "CC"),
        valid_until=(datetime.now(timezone.utc) + timedelta(days=1)).timestamp(),
        requires_human_approval_above=SettlementCredit(500, "CC"),
        signature="ed25519:demo",
    )
