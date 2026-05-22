# NeuralClear Whitepaper

## Abstract

NeuralClear is a prototype clearing layer for AI agent-to-agent service markets. It models the minimum objects needed for agents to discover capabilities, request prices, spend under bounded authorization, receive verifiable task results, and settle balances.

## Motivation

As agents become service consumers and service providers, they need an economic protocol as much as a communication protocol. A task request alone does not answer who is allowed to spend, how much the provider can charge, what evidence backs the output, or what happens when the buyer disputes the work.

NeuralClear focuses on that settlement surface.

## Design Goals

- Keep agent service payments explicit and auditable.
- Separate resource measurement from settlement credit.
- Represent delegated spending with bounded mandates.
- Define a simple lifecycle that can support disputes and refunds.
- Keep the prototype small enough to inspect and test.

## Non-Goals

- Production custody
- Real-world compliance
- Real TEE attestation
- ZK proof verification
- Decentralized consensus
- Complex pricing markets

## Protocol Sketch

1. Provider publishes an Agent Manifest with identity, endpoint, public key, capabilities, prices, and reputation.
2. Buyer discovers providers by capability.
3. Buyer requests a quote containing resource estimates and settlement price.
4. Buyer checks a Spending Mandate before accepting the quote.
5. Provider runs the task and returns a result plus proof metadata.
6. Buyer verifies proof according to the advertised proof level.
7. Ledger settles a strictly zero-sum transfer from sender to receiver, with explicit fees sent to `fee_pool`.
8. Disputes may resolve to settlement, refund, or slashing.

## Economic Invariant

For every settled transaction:

```text
sender pays receiver
amount > 0
fee >= 0
sum(account_deltas) + fee_pool_delta = 0
```

No hidden tolerance is allowed.

## Security Model

The current repository is an executable prototype. `MockProof` is a placeholder and should never be used as evidence of trustworthy execution. Real deployments would need authenticated manifests, signature verification, replay protection, privacy controls, fraud monitoring, dispute governance, and secure settlement rails.

## Current Status

Prototype / not production ready.
