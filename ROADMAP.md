# NeuralClear Roadmap

## Positioning

NeuralClear is an open clearing and trust protocol for AI agent service transactions.

It does not replace MCP, A2A, AP2, or x402. It composes with them:

- MCP and A2A help agents connect and communicate.
- AP2 and x402 can help authorize or execute payment.
- NeuralClear defines how service transactions are quoted, authorized, verified, settled, disputed, and audited.

## Prototype status

This repository is a prototype. It is not production ready and it does not custody funds.

On the opt-in `neuralclear-escrow-v1` profile:

- Stripe channel adapter (`ClearingLedger` in `neuralclear.escrow_channel`, `StripeChannel`). It submits test-mode processor calls. Stripe is not legal escrow. The checked-in `docs/p0-live-stripe-*` notes are historical records: a test-mode charge and a JPY Transfer were created, and the bank payout (`po_`) was not. They are not a production certification.
- Ed25519 signatures (pure Python, RFC 8032) for that profile's mandates, result proofs, and receipts. The implementation is not constant-time and is not a production signer.
- Strict escrow, an append-only journal, and an independent verifier.

Still not done:

- x402 adapter
- Stablecoin settlement. `StablecoinChannel` is a design-only port: no chain client, token transfer, or finality.
- Production custody, safeguarding, and compliance
- TEE attestation and ZK proof verification (`TEEVerifier` and `ZKVerifier` are interfaces only)

The default commercial path (`neuralclear.clearing`, the gateway, and netting) still settles internal credits and signs receipts with HMAC-SHA256.

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

- Internal credits — present as prototype ledger balances and commercial credit holds. Not legal escrow.
- Stripe adapter — present only on the opt-in `neuralclear-escrow-v1` profile. Not production custody.
- x402 adapter — not started
- Stablecoin adapter — not started. The port specification does not move tokens.

NeuralClear should produce settlement receipts and adapter instructions without becoming a custodial wallet.

## V0.5: Marketplace Demo

Not a shipped marketplace. Mandate checks, receipts, disputes, and fee accounting exist inside the prototype clearing layer, and the reference server has a dashboard. That is not a hosted buyer or provider product.

- Buyer dashboard
- Provider dashboard
- Mandate management
- Transaction history
- Receipts
- Disputes
- Basic platform fee accounting

## V1.0: Commercial Infrastructure

Not production infrastructure. The gateway and reference server have prototype API keys and isolated tenant workspaces. Webhooks, audit-grade logs, SLA reporting, and enterprise deployment are not done.

- API keys
- Team accounts
- Webhooks
- Audit logs
- Private registry
- SLA reporting
- Provider verification
- Enterprise deployment option
