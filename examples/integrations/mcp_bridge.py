"""MCP bridge: clear commercial usage around MCP-style tool calls.

Positioning demo. MCP connects agents to tools; NeuralClear adds the
commercial layer: who pays, how much, under what mandate, with what
receipt. This example wraps an "MCP tool" (any callable) as a priced
NeuralClear capability, then runs a buyer purchase against it.

Run:
    python3 examples/integrations/mcp_bridge.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from neuralclear.buyer import BuyerAgent
from neuralclear.core import AgentRegistry, Ledger, SettlementCredit, SpendingMandate
from neuralclear.provider import ProviderAgent


# ----------------------------------------------------------------------
# 1. Pretend MCP tool. In a real deployment this is an MCP server tool
#    invocation (e.g. a web-search or code-review tool behind MCP).
# ----------------------------------------------------------------------
def mcp_web_search_tool(payload: object) -> dict[str, object]:
    query = payload.get("query", "") if isinstance(payload, dict) else str(payload)
    return {
        "tool": "mcp.web_search",
        "query": query,
        "results": [
            {"title": f"Result for {query}", "url": "https://example.com/1"},
            {"title": f"More on {query}", "url": "https://example.com/2"},
        ],
    }


def main() -> None:
    # ------------------------------------------------------------------
    # 2. Provider side: wrap the MCP tool as a priced capability.
    #    This is the entire integration for a provider developer.
    # ------------------------------------------------------------------
    provider = ProviderAgent("agent.mcp_search", endpoint="https://search.example.com")

    @provider.capability("search.web", price=5, resource_estimate=1, resource_unit="queries")
    def search(payload: object) -> object:
        return mcp_web_search_tool(payload)

    # ------------------------------------------------------------------
    # 3. Buyer side: owner grants a bounded mandate, buyer purchases.
    # ------------------------------------------------------------------
    registry = AgentRegistry()
    ledger = Ledger()
    ledger.open_account("owner.acme", SettlementCredit(100))
    ledger.open_account("agent.mcp_search", SettlementCredit(0))

    mandate = SpendingMandate(
        owner="owner.acme",
        agent="buyer.assistant",
        allowed_capabilities=["search.web"],
        max_per_task=SettlementCredit(10),
        max_daily=SettlementCredit(50),
        valid_until=float("inf"),
        requires_human_approval_above=SettlementCredit(25),
        signature="ed25519:demo",
    )

    buyer = BuyerAgent(
        "buyer.assistant",
        registry=registry,
        ledger=ledger,
        mandate=mandate,
        owner="owner.acme",
    )
    buyer.connect_local(provider)

    outcome = buyer.purchase("search.web", payload={"query": "agent clearing protocols"})

    # ------------------------------------------------------------------
    # 4. What products get back: result + receipt + moved balances.
    # ------------------------------------------------------------------
    print("=== MCP tool output (delivered through NeuralClear) ===")
    print(json.dumps(outcome.result.output, indent=2))
    print()
    print("=== SettlementReceipt ===")
    print(json.dumps(outcome.receipt, indent=2))
    print()
    print("=== Ledger after settlement ===")
    print(json.dumps(ledger.snapshot(), indent=2))


if __name__ == "__main__":
    main()
