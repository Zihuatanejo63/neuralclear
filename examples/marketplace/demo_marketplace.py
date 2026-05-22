from __future__ import annotations

from pathlib import Path
from pprint import pprint
from uuid import uuid4
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from examples.marketplace.buyer_research_agent import research_buyer_mandate
from server.ledger_store import ReferenceClearingService
from server.registry import manifest_for


def main() -> None:
    service = ReferenceClearingService()
    buyer = "buyer.research"
    provider = "agent.pdf_summarizer"
    capability = "summarize.pdf"

    print("1. Discover provider manifest")
    manifest = manifest_for(service.registry.get(provider))
    pprint(manifest)

    print("\n2. Request quote")
    quote = service.request_quote(provider, capability)
    pprint(quote)

    print("\n3. Submit task with mandate")
    task = service.submit_task(
        task_id=f"task_{uuid4().hex}",
        quote_id=str(quote["quote_id"]),
        buyer=buyer,
        provider=provider,
        payload={
            "filename": "neuralclear-whitepaper.pdf",
            "text": (
                "NeuralClear defines quote, mandate, proof, settlement, and dispute "
                "semantics for AI agent service transactions. It is a protocol "
                "prototype, not a production payment system."
            ),
        },
        mandate=research_buyer_mandate(),
    )
    pprint(task)

    print("\n4. Settlement receipt")
    receipt = task["result"]["receipt"]
    pprint(receipt)

    print("\n5. Balances snapshot")
    pprint(service.balances_snapshot())


if __name__ == "__main__":
    main()
