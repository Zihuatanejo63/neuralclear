"""Reputation engine: transaction history drives trust and discovery.

Foundation for "Verified Provider" certification (COMMERCIALIZATION.md):
settlements raise a provider's score, disputes and slashes lower it, and
`rank_providers()` orders discovery results so reliable agents win work.

Scoring model (transparent, replaceable):

    score = base 50
          + settled * 2          (capped contribution at 40)
          - disputed * 5
          - slashed * 15
          clamped to [0, 100]

A provider with no history scores 50 (neutral), so newcomers are neither
buried nor artificially boosted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .core import AgentInfo, AgentRegistry


@dataclass
class ReputationRecord:
    agent_id: str
    settled: int = 0
    disputed: int = 0
    slashed: int = 0
    refunded: int = 0
    volume: int = 0  # total settled credits
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def score(self) -> float:
        earned = min(self.settled * 2, 40)
        penalty = self.disputed * 5 + self.slashed * 15
        return float(max(0, min(100, 50 + earned - penalty)))

    @property
    def dispute_rate(self) -> float:
        total = self.settled + self.disputed + self.slashed + self.refunded
        if total == 0:
            return 0.0
        return (self.disputed + self.slashed) / total

    def to_json(self) -> dict[str, object]:
        return {
            "agent_id": self.agent_id,
            "score": self.score,
            "settled": self.settled,
            "disputed": self.disputed,
            "slashed": self.slashed,
            "refunded": self.refunded,
            "volume": self.volume,
            "dispute_rate": round(self.dispute_rate, 4),
            "updated_at": self.updated_at.isoformat(),
        }


class ReputationEngine:
    def __init__(self) -> None:
        self._records: dict[str, ReputationRecord] = {}

    def record(self, agent_id: str) -> ReputationRecord:
        if agent_id not in self._records:
            self._records[agent_id] = ReputationRecord(agent_id=agent_id)
        return self._records[agent_id]

    # -- event hooks (wire to ClearingService.events) -----------------------
    def on_settled(self, agent_id: str, amount: int = 0) -> None:
        rec = self.record(agent_id)
        rec.settled += 1
        rec.volume += amount
        rec.updated_at = datetime.now(timezone.utc)

    def on_disputed(self, agent_id: str) -> None:
        rec = self.record(agent_id)
        rec.disputed += 1
        rec.updated_at = datetime.now(timezone.utc)

    def on_slashed(self, agent_id: str) -> None:
        rec = self.record(agent_id)
        rec.slashed += 1
        rec.updated_at = datetime.now(timezone.utc)

    def on_refunded(self, agent_id: str) -> None:
        rec = self.record(agent_id)
        rec.refunded += 1
        rec.updated_at = datetime.now(timezone.utc)

    # -- queries -------------------------------------------------------------
    def score_of(self, agent_id: str) -> float:
        return self.record(agent_id).score

    def rank_providers(self, registry: AgentRegistry, capability: str) -> list[AgentInfo]:
        """Discovery, ordered by reputation (highest first)."""
        agents = registry.discover(capability)
        return sorted(agents, key=lambda a: self.score_of(a.agent_id), reverse=True)

    def attach(self, clearing: "object") -> None:
        """Subscribe to a ClearingService's event bus so reputation updates
        automatically as transactions clear and disputes resolve."""
        from .clearing import (  # local import avoids cycle at module load
            EVENT_DISPUTE_OPENED,
            EVENT_DISPUTE_RESOLVED,
            EVENT_RECEIPT_CREATED,
            ClearingService,
        )

        if not isinstance(clearing, ClearingService):
            raise TypeError("attach() expects a ClearingService")

        def on_receipt(_event: str, payload: dict[str, object]) -> None:
            self.on_settled(str(payload.get("provider")), int(payload.get("amount", 0)))

        def on_dispute(_event: str, payload: dict[str, object]) -> None:
            tx = clearing._get_tx(str(payload.get("transaction_id")))
            self.on_disputed(tx.receiver)

        def on_resolved(_event: str, payload: dict[str, object]) -> None:
            tx = clearing._get_tx(str(payload.get("transaction_id")))
            resolution = payload.get("resolution")
            if resolution == "slash":
                self.on_slashed(tx.receiver)
            elif resolution == "refund":
                self.on_refunded(tx.receiver)
            elif resolution in {"settle", "split"}:
                self.on_settled(tx.receiver, int(payload.get("provider_amount") or tx.amount.amount))

        clearing.events.subscribe(EVENT_RECEIPT_CREATED, on_receipt)
        clearing.events.subscribe(EVENT_DISPUTE_OPENED, on_dispute)
        clearing.events.subscribe(EVENT_DISPUTE_RESOLVED, on_resolved)
