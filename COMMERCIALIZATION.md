# Commercialization Notes

## Principle

Protocol open, infrastructure commercial.

The protocol itself should remain open so agents, providers, and platforms can interoperate. Revenue should come from hosted infrastructure, registry services, verification, observability, gateways, adapters, and marketplace transactions.

## What NeuralClear Can Sell

- NeuralClear Cloud: hosted registry, quote, mandate, receipt, dispute, and reputation services
- Private registry for teams and enterprises
- Verified Provider certification
- Payment and settlement adapters
- API keys, webhooks, audit logs, and dashboards
- Marketplace transaction fees once there is real usage

## First Commercial Demo

Build a pay-per-call agent marketplace clearing layer.

Example:

- Buyer Agent: Research Assistant
- Provider Agent: PDF Summarizer
- Price: 5 CC per document in the prototype
- Mandate: max 30 CC per task, max 100 CC per day
- Result: summary, mock proof, settlement receipt
- Settlement: internal credit

Demo flow:

1. Provider publishes `/.well-known/neuralclear/agent.json`.
2. Buyer discovers `summarize.pdf`.
3. Buyer requests a quote.
4. Buyer checks a spending mandate.
5. Provider executes the task.
6. Provider returns a result and proof metadata.
7. NeuralClear records settlement.
8. Buyer and provider can inspect receipts.
9. A dispute can move the transaction to refund, slash, or settle.

## Avoid

- Issuing a token
- Custodying funds in the protocol prototype
- Marketing the project as a bank, wallet, or money transmitter
- Claiming real TEE, ZK, or signature verification before it exists

## Near-Term Product Surface

- Developer docs
- Python SDK
- TypeScript SDK
- MCP adapter
- A2A adapter
- x402 adapter
- Registry demo
- Provider and buyer dashboards
