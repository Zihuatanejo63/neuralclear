# Ledger boundary

Commercial fiat and sandbox credits are different ledgers. They do not convert.

## Rules

1. Commercial fiat uses `neuralclear.escrow` and `neuralclear.escrow_channel` as the funds source of truth. On the Stripe path the class is `ClearingLedger`. Its `currency` is one lowercase ISO code, and every balance is an integer number of minor units of that currency. The first fiat rail is Stripe Connect. This repository does not build in-house custody.
2. `neuralclear.clearing` is only for protocol semantics and the sandbox. `SettlementCredit`, `FeePolicy`, `ProviderAgent`, and `ClearingGateway` accept the currency code `CC` and nothing else. A refund there moves credits inside that ledger.
3. There is no automatic credit-to-fiat or fiat-to-credit conversion, including a 1:1 relabeling. `neuralclear.ledger_boundary.convert_credit_to_fiat` and `convert_fiat_to_credit` always raise `ProtocolError`. No rate table exists.
4. A `CC` label on `neuralclear.escrow.EscrowLedger` is that profile's own integer unit for protocol vectors. It is still not a `neuralclear.clearing` balance. `ClearingLedger` refuses `CC`, so the Stripe-attached ledger cannot be denominated in sandbox credits.

## What is enforced

| Attempt | Result |
| --- | --- |
| `ClearingLedger(currency="CC")` or any non-lowercase-ISO code | `ProtocolError` |
| `SettlementCredit`, `FeePolicy`, or `ProviderAgent` with a fiat code | `ProtocolError` |
| `StripeChannel` constructed with `neuralclear.clearing.EscrowLedger` or `ClearingService` | `ProtocolError` |
| `StripeChannel` amount whose currency is `CC` | `ProtocolError` before any HTTP call |
| `ClearingGateway` given an escrow ledger or a `StripeChannel` | `ProtocolError` |
| `server.escrow_api.create_escrow_app` given the credit ledger | `ProtocolError` |

`tests/test_ledger_boundary.py` locks these refusals.

## How HTTP attaches

### Sandbox credit gateway

Do not use this for card charges, Connect transfers, or payouts.

- Modules: `neuralclear.gateway`, `neuralclear.clearing`, `neuralclear.netting`, `neuralclear.store`
- Constructor: `ClearingGateway(clearing=ClearingService(), api_key=...)`. The default service is the credit ledger. Passing `neuralclear.escrow.EscrowLedger`, `ClearingLedger`, or `StripeChannel` is rejected.
- Endpoints, all in credit units: `POST /v1/accounts`, `POST /v1/clear`, `POST /v1/channels`, `POST /v1/channels/{id}/meter`, `POST /v1/channels/{id}/settle`, `POST /v1/disputes`, `POST /v1/disputes/{id}/resolve`, `GET /v1/ledger`, `GET /v1/receipts/{id}`
- Auth: `X-NeuralClear-Api-Key` when `api_key` is set
- Must not be wired to `StripeChannel`, `Funding`, or a fiat `ClearingLedger`

### Fiat profile HTTP

This is the opt-in `neuralclear-escrow-v1` surface. It talks to the fiat ledger. It does not call Stripe itself.

- Modules: `server.escrow_api.create_escrow_app`, `neuralclear.escrow_channel.EscrowWorkflow`, `neuralclear.escrow.EscrowLedger` or `ClearingLedger`
- The ledger argument must be an `neuralclear.escrow.EscrowLedger` (including `ClearingLedger`). A credit `EscrowLedger` or `ClearingService` is rejected.
- Deploy it as its own app or mount it under `/escrow`. Do not register these routes on `ClearingGateway`.
- Endpoints: `GET /.well-known/neuralclear/agent.json`, `POST /neuralclear/quote`, `POST /neuralclear/tasks`, `GET /neuralclear/tasks/{task_id}`, `POST /neuralclear/disputes`, `GET /neuralclear/receipts/{receipt_id}`
- Required headers on the versioned routes: `X-NeuralClear-Profile: neuralclear-escrow-v1`, `X-NeuralClear-Version: 1`. Writes also send `X-NeuralClear-API-Key` equal to the operator-supplied `write_key`.
- Currency advertised by discovery is `ledger.currency`. For a Stripe-attached ledger that is the ISO code, not `CC`.

### Stripe adapter

`neuralclear.stripe_channel.StripeChannel` is bound only to a fiat `ChannelLedger` implementation, in this tree `ClearingLedger`. The operator calls `create_deposit`, `confirm_deposit`, `payout`, and `reconcile_payout`. Those methods are not mounted on `/v1/*` and are not mounted on `/neuralclear/*`. A deposit credits the fiat ledger's buyer balance after Stripe reports `succeeded`. It does not call `neuralclear.clearing`.

Buyer "refunds" inside `neuralclear.escrow` and `neuralclear.clearing` return internal balances only. `StripeChannel` has no refund method. Card refunds are specified in [stripe-live-settlement-design.md](stripe-live-settlement-design.md) and are not implemented.

## Public site

`index.html` and `site.js` still cite commit `54bd57f` and link files on that commit. On that commit, `ClearingLedger` lived in `neuralclear/clearing.py`. Those pages were not rewritten. They describe the pre-rebase branch, not the module layout in this tree.
