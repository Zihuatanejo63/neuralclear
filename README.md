# NeuralClear

NeuralClear is an open clearing and trust protocol prototype for AI agent-to-agent service transactions.

It standardizes how agents quote, authorize, execute, verify, settle, and dispute service transactions. NeuralClear does not issue money, custody funds, or replace payment rails; it defines the transaction semantics around agent services.

## Why NeuralClear

Agent ecosystems need more than message passing. A buyer agent needs to know:

- which provider can perform a capability
- how the task is priced
- whether it is authorized to spend on behalf of an owner
- what proof level comes with the result
- how balances move after settlement
- how disputes, refunds, slashing, and expiration are represented

NeuralClear is a small Python protocol prototype for those clearing semantics. Actual payment can be handled by adapters such as internal credits, Stripe, stablecoins, x402-style HTTP payment, or other rails.

## Core Flow

```mermaid
flowchart LR
  A["Buyer agent"] -->|QUOTE_REQUESTED| B["Provider agent"]
  B -->|Quote: resource estimate + settlement price| A
  A -->|Mandate check + QUOTE_ACCEPTED| L["NeuralClear ledger"]
  A -->|TASK_SUBMITTED| B
  B -->|TASK_RUNNING / RESULT_DELIVERED| A
  A -->|PROOF_VERIFIED| L
  L -->|SETTLED: sender pays receiver| C["Balances + fee_pool"]
  A -->|DISPUTED| D["Refund / Slash / Settle"]
```

`Transaction.amount > 0` always means `sender` pays `receiver`.

## Quick Run

```bash
python3 examples/demo.py
python3 -m unittest discover
```

The demo prints a `TaskResult` and ledger snapshot. Tests cover payment direction, insufficient credit, zero-sum clearing, registration, discovery, mandate limits, quote expiration, and dispute state transitions.

## HTTP Draft

The draft HTTP surface is in [OPENAPI.yaml](OPENAPI.yaml). A provider can expose a manifest at:

```text
/.well-known/neuralclear/agent.json
```

See [examples/well-known/agent.json](examples/well-known/agent.json) for a concrete manifest.

## Protocol Objects

`ResourceUnit` measures resources such as tokens, GPU seconds, bandwidth, or storage.

```json
{ "amount": 8000, "unit": "tokens" }
```

`SettlementCredit` is the value used for clearing.

```json
{ "amount": 25, "currency": "CC" }
```

`AgentInfo` advertises identity, endpoint, public key, capabilities, pricing, and reputation. See [examples/agent_manifest.json](examples/agent_manifest.json) and [schemas/agent_manifest.schema.json](schemas/agent_manifest.schema.json).

`SpendingMandate` delegates spending authority from an owner to an agent, bounded by capability, per-task amount, daily amount, expiration, and human-approval threshold. See [examples/spending_mandate.json](examples/spending_mandate.json).

`Quote` binds a provider, capability, resource estimate, settlement price, and expiration. See [examples/quote.json](examples/quote.json).

`Transaction` records sender, receiver, settlement amount, optional fee, capability, quote, and lifecycle state. See [examples/transaction.json](examples/transaction.json).

`TaskResult` returns output, resource usage, settlement amount, and a proof object. See [examples/task_result.json](examples/task_result.json).

## Proof Levels

The current implementation includes `MockProof` for local development only. It is not a real TEE proof.

Supported proof level names:

- `NONE`
- `SIGNED_RESULT`
- `REPRODUCIBLE`
- `TEE_ATTESTATION`
- `ZK_PROOF`

## Relationship To A2A, MCP, AP2, And x402

- A2A lets agents communicate and coordinate. NeuralClear adds quote, mandate, settlement, proof, receipt, dispute, and reputation semantics around commercial service transactions.
- MCP connects models and agents to tools, data, and workflows. NeuralClear can clear commercial usage around MCP-style tool calls.
- AP2-style authorization motivates `SpendingMandate`: an owner can grant bounded spending authority without giving an agent unlimited payment power.
- x402-style payment-gated HTTP can execute machine-native payment. NeuralClear can decide when payment is due and produce the receipt, proof, and dispute record around it.

NeuralClear is intended to compose with these protocols, not replace them.

## Current Status

Current stage: V0.1 protocol prototype.

Next milestone: HTTP reference implementation.

Prototype only. Not production ready.

This repository does not implement real custody, real payment execution, real TEE attestation, real ZK verification, identity recovery, compliance, finality guarantees, or adversarial dispute resolution. Treat it as a protocol sketch with executable tests.

Suggested GitHub About text:

```text
Prototype clearing, authorization, proof, and dispute layer for AI agent-to-agent service transactions.
```
