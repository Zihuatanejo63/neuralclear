from __future__ import annotations

from html import escape

try:
    from fastapi.responses import HTMLResponse
except ModuleNotFoundError:  # pragma: no cover - routes register only when FastAPI exists.
    HTMLResponse = None


def register_dashboard_routes(app, service, registry_store) -> None:
    def page(title: str, rows: list[str]) -> str:
        body = "\n".join(rows) or "<p>Empty.</p>"
        return (
            "<!doctype html><html><head>"
            f"<title>{escape(title)}</title>"
            "<style>body{font-family:system-ui;margin:2rem;max-width:960px}"
            "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px}"
            "code{background:#f4f4f4;padding:2px 4px}</style>"
            "</head><body>"
            f"<h1>{escape(title)}</h1>{body}</body></html>"
        )

    @app.get("/dashboard/agents", response_class=HTMLResponse)
    def dashboard_agents():
        rows = [
            f"<tr><td><code>{escape(str(agent['agent_id']))}</code></td>"
            f"<td>{escape(str(agent['name']))}</td>"
            f"<td>{escape(', '.join(map(str, agent.get('capabilities', []))))}</td></tr>"
            for agent in registry_store.list_agents()
        ]
        return page("Agents", ["<table><tr><th>ID</th><th>Name</th><th>Capabilities</th></tr>", *rows, "</table>"])

    @app.get("/dashboard/transactions", response_class=HTMLResponse)
    def dashboard_transactions():
        rows = [
            f"<tr><td><code>{escape(tx.transaction_id)}</code></td>"
            f"<td>{escape(tx.sender)}</td><td>{escape(tx.receiver)}</td>"
            f"<td>{tx.amount.amount}</td><td>{tx.fee.amount}</td><td>{escape(tx.state.value)}</td></tr>"
            for tx in service.ledger.transactions
        ]
        return page(
            "Transactions",
            ["<table><tr><th>ID</th><th>Sender</th><th>Receiver</th><th>Amount</th><th>Fee</th><th>State</th></tr>", *rows, "</table>"],
        )

    @app.get("/dashboard/receipts", response_class=HTMLResponse)
    def dashboard_receipts():
        rows = [
            f"<tr><td><code>{escape(receipt.receipt_id)}</code></td>"
            f"<td><code>{escape(receipt.transaction_id)}</code></td>"
            f"<td>{escape(receipt.sender)}</td><td>{escape(receipt.receiver)}</td>"
            f"<td>{receipt.amount['amount']}</td><td>{receipt.fee['amount']}</td></tr>"
            for receipt in service.receipts.values()
        ]
        return page(
            "Receipts",
            ["<table><tr><th>ID</th><th>Transaction</th><th>Sender</th><th>Receiver</th><th>Amount</th><th>Fee</th></tr>", *rows, "</table>"],
        )

    @app.get("/dashboard/disputes", response_class=HTMLResponse)
    def dashboard_disputes():
        rows = [
            f"<tr><td><code>{escape(str(dispute['dispute_id']))}</code></td>"
            f"<td><code>{escape(str(dispute['transaction_id']))}</code></td>"
            f"<td>{escape(str(dispute['reason']))}</td><td>{escape(str(dispute['state']))}</td></tr>"
            for dispute in service.disputes.values()
        ]
        return page(
            "Disputes",
            ["<table><tr><th>ID</th><th>Transaction</th><th>Reason</th><th>State</th></tr>", *rows, "</table>"],
        )

    @app.get("/dashboard/balances", response_class=HTMLResponse)
    def dashboard_balances():
        snapshot = service.balances_snapshot()
        balances = snapshot["balances"]
        rows = [
            f"<tr><td>{escape(account)}</td><td>{amount}</td></tr>"
            for account, amount in dict(balances).items()
        ]
        rows.extend(
            [
                f"<tr><td>fee_pool</td><td>{snapshot['fee_pool']}</td></tr>",
                f"<tr><td>total_supply</td><td>{snapshot['total_supply']}</td></tr>",
            ]
        )
        return page("Balances", ["<table><tr><th>Account</th><th>Amount</th></tr>", *rows, "</table>"])
