# Stripe test-mode payout continuation: 2026-10-22

## Outcome: blocked before connected-account creation

A real Stripe API request was made using the existing test credential from
`~/.config/neuralclear/stripe.env`. Stripe rejected creation because this platform
has not signed up for Connect. Per the requested stop condition, no further
onboarding or funds operations were attempted. No fake fallback was used.

## Platform and country selection

`GET /v1/account` confirmed:

- Platform: `acct_1TQJQcE5PKlMxr4M` (NOT a provider destination).
- Country: `JP`; default currency: `jpy`.
- `charges_enabled=false`; `payouts_enabled=false`.

Selected `JP` for the proposed Custom connected account to match the platform
country rather than introduce a cross-border transfer. Requested the `transfers`
capability. Account v1 payout readiness is checked via `payouts_enabled` and its
requirements/external bank account, not a fabricated `payouts` capability.

The existing internal settlement remains **50 USD minor units (USD 0.50)**.
Japan/Japanese-bank JPY settlement is not interchangeable with this USD claim.
No currency conversion or balance relabeling was performed. Connected-account
currency support, bank setup, FX reconciliation and payout liquidity remain
unverified because account creation failed first.

References: [Connect testing](https://docs.stripe.com/connect/testing),
[account creation](https://docs.stripe.com/api/accounts/create),
[cross-border payouts](https://docs.stripe.com/connect/cross-border-payouts-to-recipients).

## Actual API attempt

`POST /v1/accounts`, using test-mode authentication:

```json
{
  "type": "custom",
  "country": "JP",
  "capabilities[transfers][requested]": "true",
  "metadata[neuralclear_transaction]": "nc_stripe_test_aafa336c0da8416a9bcc34c96cae4abe"
}
```

Idempotency key: `nc-payout-20261022-provider-jp-v1`.

Stripe returned HTTP **400**, Request-Id **`req_8gPGnFl3Yfa1Vh`**.
Original error fields (no credentials or request headers included):

```json
{
  "type": "invalid_request_error",
  "message": "You can only create new accounts if you've signed up for Connect, which you can do at https://dashboard.stripe.com/connect. Alternatively, you can enable Connect using the Stripe MCP (search for 'EnableConnect' using the stripe_api_search tool) or use the Stripe CLI to run 'stripe tools search enable_connect'"
}
```

Allowlisted response evidence is also saved locally at
`/private/tmp/neuralclear-stripe-live-20261022/connect-attempt.json` (mode 0600).

## Object inventory and funds actions

| Object | ID | This attempt |
| --- | --- | --- |
| Provider connected account | None | Creation rejected; no account returned |
| Transfer | None | Not attempted |
| Connected-account payout | None | Not attempted |
| Original PaymentIntent | `pi_3UTEXcE5PKlMxr4M1BLslkNm` | Existing; no new charge |
| Original charge | `ch_3UTEXcE5PKlMxr4M1o0whdoo` | Existing; no transfer attached |

There are no `tr_` or `po_` objects to retrieve or claim `livemode=false` for.
No bank account was attached, and no test identity or terms acceptance was
submitted. The platform was not substituted for a provider.

## Internal chain and independent verification

The intended continuation was the original transaction
`nc_stripe_test_aafa336c0da8416a9bcc34c96cae4abe`. Its prior settlement remains
unchanged. Account creation failed before any payout reservation or ledger
mutation; no replacement transaction was created and no receipt was reissued.

Reverified the **original, pre-payout receipt** with the independent CLI:

```sh
/tmp/neuralclear-stripe-tests/bin/python -m neuralclear.verify \
  /private/tmp/neuralclear-stripe-live-20261022/receipt.json \
  /private/tmp/neuralclear-stripe-live-20261022/chain.json \
  --algorithm Ed25519 --key-id clearing \
  --key-file /private/tmp/neuralclear-stripe-live-20261022/public.key
```

Result: **VALID**, exit code **0**. This verifies the internal receipt and
metering chain, NOT an external payout. A payout-complete receipt does not exist.

Regression command: `/tmp/neuralclear-stripe-tests/bin/python -m pytest tests/ -q`.
Result: **130 passed, 243 subtests passed**. Tests do not make real Stripe calls.

## Required next action

The account owner must enable Stripe Connect for this platform before retrying.
This run intentionally did not enable Connect after the explicit API rejection.
After that, re-check same-country account capabilities and bank/currency support,
then resolve the USD ledger versus JPY settlement mapping before transferring.
Only actual retrieved Transfer/Payout objects may be recorded, and a pending
payout must not be described as paid. No commits or pushes were made.
