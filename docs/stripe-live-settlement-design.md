# Stripe live settlement design

Status: design only. This document does not enable live mode. Do not connect live keys. Do not create live charges, payouts, refunds, or transfers while implementing from this text until a later change explicitly turns live mode on and reviews the stop rules below.

The decisions below are locked. An implementation phase should not reopen them.

## Locked decisions

- The first fiat path is Stripe Connect. NeuralClear does not build in-house fund custody. Stripe holds and moves the money. NeuralClear stores the ledger record and the Stripe object ids.
- Fiat balances live on `neuralclear.escrow` / `neuralclear.escrow_channel.ClearingLedger`. That ledger is the funds source of truth. Integer amounts are minor units of one lowercase ISO currency.
- `neuralclear.clearing` is the `CC` sandbox. Live settlement code must not import it, construct it, or post a balance into it.
- No automatic conversion either way, and no 1:1 relabeling of `CC` as cents. `neuralclear.ledger_boundary` refuses both directions.
- The profile is opt-in `neuralclear-escrow-v1`. The legacy SDK and `ClearingGateway` `/v1/*` routes stay on credits. See [ledger-boundary.md](ledger-boundary.md).
- A Stripe HTTP step that fails twice stops. The process reports the step name, the HTTP status or "outcome unknown", and the idempotency key it already used. It does not send a third automatic POST.
- If the network result is unknown (`URLError`, timeout, or a dropped response), keep the same idempotency key. Do not rotate or rewrite it. The next attempt, if an operator explicitly resumes, replays that key and then re-fetches.
- A Japan platform account cannot transfer USD to a US connected account. That corridor is open and unsolved. Do not treat a JPY test-mode Transfer as evidence that this corridor works.

## What already exists (test mode and stubs)

`StripeChannel` today can:

- `connect_preflight` (GET account, GET accounts?limit=1)
- `create_connected_account` (POST accounts)
- `create_deposit` (POST payment_intents)
- `confirm_deposit` (GET payment_intents/{id}, then `ledger.credit_escrow`)
- `payment_status`, `payout_status`
- `payout` (POST transfers, then POST payouts)
- `reconcile_payout` (GET payout, then `ledger.record_payout`)

It has no `refund`, `create_refund`, or transfer-reversal method. `examples/escrow_channel_live_test.py` rejects any key that is not `sk_test_...`. Leave that rejection in place. This design does not add a live-key path.

Buyer refunds that exist today:

- `neuralclear.clearing.EscrowLedger.refund_escrow` returns sandbox `CC` to the buyer.
- `neuralclear.escrow` settlement and dispute transitions add an internal `refund` amount back to the buyer balance of that escrow ledger.

Neither of those calls Stripe. A receipt field named `refund` is not a card refund.

Historical test-mode evidence, kept as records and not re-run for this design:

- A test-mode charge and a JPY Transfer were recorded (`docs/p0-live-stripe-run-2026-10-22.md`, `docs/p0-live-stripe-payout-jp-continuation-2026-10-22.md`).
- A bank payout id (`po_`) was not achieved. The continuation report says the Transfer moved JPY into pending balance and actual bank payout was zero.
- An earlier USD settlement on the internal ledger was not converted into that JPY Transfer. The reports say no currency relabeling was performed.
- The platform country recorded in those reports is JP.

## Live charges

Live charges stay PaymentIntents on the platform account, in the ledger currency, for the exact minor-unit amount on `Funding`.

`create_deposit` already sends `amount`, `currency`, `automatic_payment_methods[enabled]`, and metadata `buyer`, `escrow_id`, `funding_key`. Keep that body. The Stripe idempotency key stays `_key("deposit", buyer, escrow_id, idempotency_key)`. The ledger binding is the caller-supplied `idempotency_key` via `bind_funding`. A changed payload for the same binding is `idempotency key conflict` and must not be retried with a new key.

Card authentication stays in the client Stripe flow. `confirm_deposit` must keep re-fetching the PaymentIntent. A webhook body, a success URL, or a client-supplied status is not proof. Credit the fiat ledger only when the fetched object matches id, `status=succeeded`, `amount`, `amount_received`, `currency`, and the three metadata fields. `livemode` must be true only when the process was started with an explicit live flag (below). In every other process, `livemode: true` is a hard error and must not credit the ledger.

Failure policy for this step:

1. HTTP 4xx with a parseable Stripe error: do not credit. Keep the same Stripe idempotency key. A second identical POST is allowed only as an operator resume of this same step, not as a loop inside the method.
2. Transport error or an unreadable body: outcome unknown. Do not credit. Do not change the key. Stop if this is the second failure of this step.
3. After two failures, stop the step and report. Do not create another PaymentIntent.

`credit_escrow` remains the only balance increase, and it writes the fiat ledger. It must not call `convert_fiat_to_credit`.

## Payouts to sellers

Model: separate charges and transfers. The platform PaymentIntent collects funds. After the fiat ledger has a final positive settlement, `payout` reserves that net amount, POSTs a Transfer to the connected account, then POSTs a Payout on that account.

Keep the current key derivation:

- Transfer: `_key("transfer", settlement_id)`
- Payout: `_key("payout", settlement_id)`

The caller's idempotency key is stored on the reservation and must not be mixed into those Stripe keys. Changing the caller key must not create a second Transfer. `reserve_settlement` already refuses a second reservation for the same settlement.

The connected account id comes from operator configuration (`ClearingLedger` `provider_accounts`), not from the buyer request and not from the task payload.

`record_payout` may persist `pending` and `in_transit`. Those states are not paid. Only `paid` reduces fiat supply. `failed` and `canceled` stay reserved. Do not automatically refund, do not release the reservation, and do not allocate a fresh Stripe key.

Before any payout POST, GET the connected-account balance and any existing payout or transfer with this settlement metadata. The historical JPY run created `tr_` and then stopped because available balance was not yet payable. A later implementation must do that GET first. If the Transfer already exists, do not POST another Transfer. If a `po_` already exists, reconcile it. If available balance is short, stop and report. Do not invent a top-up.

Failure policy matches charges: two failures stop the step; an unknown result keeps `_key("transfer", settlement_id)` or `_key("payout", settlement_id)`, whichever POST was in flight. Do not reverse a Transfer just because the following Payout POST timed out. Re-fetch both objects, then record.

## Real card refunds

Not implemented. The future method on `StripeChannel` should be the only card-refund entry point:

```text
refund_deposit(payment_intent_id, funding, *, amount, idempotency_key) -> dict
```

Required behavior when that method is written:

- Refuse a credit ledger, a `CC` amount, and any currency other than `funding.currency` and the ledger currency.
- `amount` is a positive int in minor units, less than or equal to the PaymentIntent `amount_received` still unrefunded.
- Reserve the refund on the fiat ledger first, under a durable id. The Stripe idempotency key is `_key("refund", payment_intent_id, reservation_id)`. A client key that changes does not mint a second Refund. An unknown POST keeps this key.
- Re-fetch the PaymentIntent before the POST. If its `livemode` does not match the process flag, stop.
- If a Transfer of those funds to a connected account has already been recorded, create the Stripe reversal of that Transfer (or the documented debit of the connected account) and store `trr_` / reversal id before posting the charge Refund. If the reversal outcome is unknown, do not also POST the charge Refund in the same automatic step.
- POST `/v1/refunds` with `payment_intent`, `amount`, and metadata `escrow_id` plus the reservation id. Then GET the Refund. Apply the fiat-ledger reduction only when the fetched Refund matches amount, currency, and PaymentIntent, and its status is `succeeded`. `pending` stays reserved.
- Do not increase a `neuralclear.clearing` balance. Do not call `convert_fiat_to_credit`. An internal escrow `refund` field may be updated only as a label of this fiat movement, and docs that surface it must say "card refund" only after the fetched Refund succeeded.
- Two failures of the reversal step, or two failures of the Refund POST, stop that step and report. Do not continue to the other step automatically after the second failure.

Until that method exists, callers must not describe an escrow-ledger refund as money returned to a card.

## Production webhooks and keys

No webhook route is implemented. Add one only on the fiat app, not on `ClearingGateway`.

Environment names, and no others in process config:

- `STRIPE_SECRET_KEY` — platform secret. The current live runner accepts only a test-mode secret. A future live process may read a live secret from this same variable only when the live flag is set. Never log it, never put it in the journal, and never write a value into the repo, tests, or docs.
- `STRIPE_WEBHOOK_SECRET` — Stripe endpoint signing secret for `Stripe-Signature`. Same storage rule.

Storage: the process environment, or a secret-manager reference that the process resolves at start. Do not add a new tracked file. The existing test-mode runbook's local files stay outside this design and stay test-mode only. `.gitignore` already ignores `.env`, `.env.local`, and `stripe.env`.

The live flag is an explicit operator switch, default off. Name it `NEURALCLEAR_STRIPE_MODE` with values `test` (default) and `live`. `live` without a successfully checked signature path and without the corridor allowlist below must refuse to start. Unset means `test`.

Verify `Stripe-Signature` with `STRIPE_WEBHOOK_SECRET` before parsing the event. Then GET the object by id with `STRIPE_SECRET_KEY`. The event payload is a hint, not a posting. Handle only:

- `payment_intent.succeeded` and `payment_intent.payment_failed` — GET the PaymentIntent, then the existing `confirm_deposit` checks. `payment_failed` does not credit.
- `charge.refunded` and `refund.updated` — GET the Refund. Post to the fiat ledger only through the refund reservation rules above.
- `transfer.created` and `transfer.reversed` — GET the Transfer. Match `metadata.settlement_id` to an existing reservation. Do not create a reservation from the event.
- `payout.paid`, `payout.failed`, `payout.canceled` — GET the payout and call `reconcile_payout`.
- `charge.dispute.created` — freeze the fiat escrow for that PaymentIntent and stop automatic payout. Do not move `CC`.

Ignore other event types. A signature failure is a 400 and is not retried inside the process. Stripe's own webhook retry is the remote side; the handler must be idempotent on event id and object id.

Unknown GET result: do not post, do not rotate a key, and count it as a failure of that delivery. Two failed deliveries of the same event id stop and report.

## Corridors and reconciliation

A corridor is the tuple `(platform_country, charge_currency, connected_account_country, payout_currency)`.

This phase allows a corridor only when all of the following hold:

- charge currency, transfer currency, and payout currency are the same lowercase ISO code as `ClearingLedger.currency`
- NeuralClear does not compute an exchange rate
- the tuple is on an operator allowlist loaded from configuration, not from a buyer request

The allowlist ships empty for `NEURALCLEAR_STRIPE_MODE=live`. An empty allowlist means live payout and live transfer POSTs are refused. Test mode may keep using the existing stub and the historical manual runs.

Explicitly denied, even if someone puts it on an allowlist by mistake: platform country `JP`, charge currency `usd`, connected-account country `US`. Implementation must reject that tuple in code, not only in config. The historical reports did not complete a USD transfer to a US account from the JP platform. Do not assume a later Stripe account change has removed this limit.

Reconciliation, once implemented, is read-only unless a row is already reserved:

- For each open `pi_`, `tr_`, `po_`, and future `re_` / reversal id on the fiat ledger, GET the Stripe object.
- Compare amount, currency, livemode, metadata, and status with the journal row.
- A mismatch fails closed: leave the reservation, do not POST a correcting object, do not touch the credit ledger.
- If Stripe shows an object that the ledger does not have, report it. Do not auto-adopt it by inventing a new idempotency key.
- Summing `neuralclear.clearing` balances with fiat minor units is not a reconciliation. The two totals are different units.

## Where this sits in the profile

```text
buyer card
    -> Stripe PaymentIntent on the platform
    -> confirm_deposit re-fetch
    -> ClearingLedger.credit_escrow          (fiat minor units)
    -> escrow-v1 quote / task / meter / settle
         via server.escrow_api or EscrowWorkflow
    -> ClearingLedger.reserve_settlement
    -> Stripe Transfer to the connected account
    -> Stripe Payout to the seller's bank
    -> record_payout when status is known
```

`server.escrow_api` routes do not call Stripe. A worker that owns the `StripeChannel` performs the Stripe steps. That worker's ledger argument is a `ClearingLedger`. `ClearingGateway` is not in this path.

Profile selection stays explicit: `NeuralClearSDK(..., profile="neuralclear-escrow-v1")` and an `EscrowLedger`. The default profile remains `legacy` and keeps using credits.

## Open risks

- Live mode is not implemented. Turning on `NEURALCLEAR_STRIPE_MODE=live` without the checks above would violate this design.
- Ed25519 in this repo is a pure-Python reference and is not constant-time. It is not the Stripe authenticator. Stripe requests use the platform secret.
- The JP-platform to US-account USD corridor is unsolved.
- Historical test-mode evidence includes a charge and a JPY Transfer, not a completed bank payout.
- Card refunds and transfer reversals are unspecified in code. Internal `refund` amounts are easy to misread as card refunds.
- Webhooks are unspecified in code. Posting from an unverified event body would fake a deposit.
- Stripe idempotency keys expire on Stripe's side. After expiry, an uncertain reservation stays stuck until a human reconciles by GET. The ledger must keep refusing a fresh key, which is already the `payout` comment in `stripe_channel.py`.
- Chargebacks, sanctions screening, and cross-border eligibility are not implemented.
- Connect onboarding requirements change by country. `connect_preflight` does not prove a corridor is legal or that `payouts_enabled` will stay true.
- Two ledgers can both show a balance for the same agent id. Operators must not add those numbers.

## Implementation checklist

A later change can pick this up without new product decisions if it does all of the following and no more:

- Keep the default mode `test`. Do not accept `sk_live_` in `examples/escrow_channel_live_test.py`.
- Add `refund_deposit` only on `StripeChannel`, with stubbed HTTP tests, no network.
- Add webhook verification that GETs before any ledger write, with tests that a bad signature does not post and that a fiat credit does not change a `CC` balance.
- Deny the JP / `usd` / US corridor in code.
- Leave `ClearingGateway` unable to accept a fiat ledger.
- Stop each Stripe step on the second failure, and do not rotate an idempotency key after an unknown result.
