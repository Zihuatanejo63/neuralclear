from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from .http_client import NeuralClearHTTPClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="neuralclear")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("NEURALCLEAR_BASE_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument("--api-key", default=os.environ.get("NEURALCLEAR_API_KEY"))
    subcommands = parser.add_subparsers(dest="resource", required=True)

    agents = subcommands.add_parser("agents")
    agents_sub = agents.add_subparsers(dest="action", required=True)
    agents_sub.add_parser("list")
    search = agents_sub.add_parser("search")
    search.add_argument("capability")

    agent = subcommands.add_parser("agent")
    agent_sub = agent.add_subparsers(dest="action", required=True)
    register = agent_sub.add_parser("register")
    register.add_argument("manifest")

    quote = subcommands.add_parser("quote")
    quote_sub = quote.add_subparsers(dest="action", required=True)
    request_quote = quote_sub.add_parser("request")
    request_quote.add_argument("provider")
    request_quote.add_argument("capability")
    request_quote.add_argument("--buyer", default="buyer.research")

    task = subcommands.add_parser("task")
    task_sub = task.add_subparsers(dest="action", required=True)
    submit = task_sub.add_parser("submit")
    submit.add_argument("quote_id")
    submit.add_argument("--text", required=True)
    submit.add_argument("--buyer", default="buyer.research")
    submit.add_argument("--provider", default="agent.pdf_summarizer")
    submit.add_argument("--idempotency-key")

    receipts = subcommands.add_parser("receipts")
    receipts_sub = receipts.add_subparsers(dest="action", required=True)
    receipts_sub.add_parser("list")

    balances = subcommands.add_parser("balances")
    balances.set_defaults(action="show")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = NeuralClearHTTPClient(args.base_url, api_key=args.api_key)

    if args.resource == "agents" and args.action == "list":
        output = client.list_agents()
    elif args.resource == "agents" and args.action == "search":
        output = client.search_agents(args.capability)
    elif args.resource == "agent" and args.action == "register":
        output = client.register_agent(json.loads(Path(args.manifest).read_text(encoding="utf-8")))
    elif args.resource == "quote" and args.action == "request":
        output = client.request_quote(args.buyer, args.provider, args.capability)
    elif args.resource == "task" and args.action == "submit":
        output = client.submit_task(
            {
                "buyer": args.buyer,
                "provider": args.provider,
                "quote_id": args.quote_id,
                "payload": {"text": args.text},
            },
            idempotency_key=args.idempotency_key,
        )
    elif args.resource == "receipts" and args.action == "list":
        output = client.list_receipts()
    elif args.resource == "balances":
        output = client.balances()
    else:
        raise SystemExit("unknown command")

    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
