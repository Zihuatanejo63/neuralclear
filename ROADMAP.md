# NeuralClear Roadmap

## Positioning

NeuralClear is an open clearing and trust protocol for AI agent service transactions.

It does not replace MCP, A2A, AP2, or x402. It composes with them:

- MCP and A2A help agents connect and communicate.
- AP2 and x402 can help authorize or execute payment.
- NeuralClear defines how service transactions are quoted, authorized, verified, settled, disputed, and audited.

## V0.1: Protocol Prototype

- Clean repository structure
- Protocol objects
- Python SDK demo
- JSON examples
- Agent manifest schema
- Unit tests
- CI

## V0.2: HTTP Protocol Draft

- `OPENAPI.yaml`
- `/.well-known/neuralclear/agent.json`
- Quote endpoint
- Task endpoint
- Settlement receipt endpoint
- Dispute endpoint

## V0.3: Registry Demo

- Local registry service
- Agent onboarding
- Capability search
- Endpoint health checks
- Manifest validation
- Provider reputation display

## V0.4: Payment Adapters

- Internal credits
- Stripe adapter
- x402 adapter
- Stablecoin adapter

NeuralClear should produce settlement receipts and adapter instructions without becoming a custodial wallet.

## V0.5: Marketplace Demo

- Buyer dashboard
- Provider dashboard
- Mandate management
- Transaction history
- Receipts
- Disputes
- Basic platform fee accounting

## V1.0: Commercial Infrastructure

- API keys
- Team accounts
- Webhooks
- Audit logs
- Private registry
- SLA reporting
- Provider verification
- Enterprise deployment option
