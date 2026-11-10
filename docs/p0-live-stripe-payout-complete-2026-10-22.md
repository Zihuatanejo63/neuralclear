# Stripe payout continuation, 2026-10-22: NOT COMPLETE

Checked at 2026-10-22 20:32:19 Asia/Shanghai (12:32:19 UTC).
The filename follows the requested deliverable name; it is not a success claim.
This is a new report. The previous Connect-not-enabled report remains unchanged
as a historical record. Connect activation is now confirmed by the existing
connected account; it is NOT the blocker in this run.

## Completed: repair the existing provider's test onboarding

Platform: `acct_1TQJQcE5PKlMxr4M`, JP, default currency JPY.
Reused provider: `acct_1UTL2zE5PK2LWR96`, Standard, US, default currency USD.
Initially transfers was active, payouts disabled. The only currently_due fields
were `business_profile.product_description` and `business_profile.url`.

Updated these through `POST /v1/accounts/acct_1UTL2zE5PK2LWR96`:
- URL: `https://neuralclear.org`
- Description: `Test-mode AI agent service provider; no live transactions.`
- Idempotency key: `nc-provider-profile-20261022-v1`.

The request succeeded. A subsequent GET confirmed payouts_enabled=true,
card_payments=active, transfers=active, no currently_due/past_due requirements,
and disabled_reason=null. No legal terms, new identity, or bank number was submitted.
The existing bank `ba_1UTL38E5PK2LWR96LThzYD9p` was already verified, USD and the
default for its currency. No duplicate account or bank was created.

## Transfer attempts: both explicitly rejected

Common request: `POST /v1/transfers`, amount=50, currency=usd,
destination=`acct_1UTL2zE5PK2LWR96`,
metadata[settlement_id]=`nc_stripe_test_aafa336c0da8416a9bcc34c96cae4abe`.

1. Original-charge route: source_transaction=`ch_3UTEXcE5PKlMxr4M1o0whdoo`;
   idempotency key `nc-transfer-aafa336c-source-v1`.
   HTTP 400, Request-Id `req_qpK9hJFxPlXYU7`.
2. Platform-balance fallback: source_transaction omitted;
   idempotency key `nc-transfer-aafa336c-balance-v1`.
   HTTP 400, Request-Id `req_9XLNvxfEaTn6eL`.

The two keys identify distinct request payloads. Both calls definitively failed;
no ambiguous transport result was retried under a new key. No source association
was created and no successful transfer was recorded.

Both returned the same original error fields:

```json
{
  "type": "invalid_request_error",
  "code": "transfers_not_allowed",
  "message": "Funds can't be sent to accounts located in US because it's restricted outside of your platform's region;"
}
```

## Why no new Custom/Express account or payout

`GET /v1/country_specs/JP` returned:

```json
{
  "supported_transfer_countries": ["JP"],
  "supported_bank_account_currencies": {"jpy": ["JP"]}
}
```

The failure is geographic, not a Standard onboarding limitation. Creating
another US account with a different type does not address the stated restriction.
A JP provider would require a JPY banking/settlement route and explicit FX
accounting, not an unchanged USD 50-minor-unit payout. That is a separate flow,
not a legitimate way to label this USD settlement as paid.

Final API balance checks (both livemode=false):

| Account | Available | Pending |
| --- | --- | --- |
| JP platform | JPY 0 | JPY 73 |
| US provider | USD 0 | USD 0 |

There is no platform USD available balance for the fallback either, although
Stripe rejected it for region before returning a balance error. A payout on the
empty provider would not demonstrate receipt of this transfer. No payout POST
was made. No platform payout, direct provider charge or unrelated funding was
used as substitute evidence.

## Acceptance status and object inventory

| Object | ID | Verified result |
| --- | --- | --- |
| Original PaymentIntent | `pi_3UTEXcE5PKlMxr4M1BLslkNm` | GET succeeded; 50 usd, succeeded, livemode=false |
| Original charge | `ch_3UTEXcE5PKlMxr4M1o0whdoo` | GET succeeded; 50 usd, livemode=false |
| Provider | `acct_1UTL2zE5PK2LWR96` | GET succeeded; payouts enabled, transfers active |
| Test bank | `ba_1UTL38E5PK2LWR96LThzYD9p` | Existing external account, verified, usd |
| Transfer | None | Both creation attempts rejected; no tr_ to GET |
| Payout | None | Not attempted; no po_ to GET |

Account v1 does not provide a livemode field; no false account marker is asserted.
Only the test-prefixed credential was used. Evidence JSON is restricted to IDs,
amounts, currencies, status/mode flags and observation time; errors and request
details are recorded here instead. Private allowlisted request history remains
at `/private/tmp/neuralclear-stripe-live-20261022/payout-continuation.json`.

## Ledger, verification and tests

No ledger mutation, payout reservation, replacement payment or receipt reissue.
The original internal transaction remains settled but NOT externally paid.
Reverified the original receipt in a separate process:

```sh
/tmp/neuralclear-stripe-tests/bin/python -m neuralclear.verify \
  /private/tmp/neuralclear-stripe-live-20261022/receipt.json \
  /private/tmp/neuralclear-stripe-live-20261022/chain.json \
  --algorithm Ed25519 --key-id clearing \
  --key-file /private/tmp/neuralclear-stripe-live-20261022/public.key
```

Result: **VALID**, exit **0**. This is internal clearing verification, not bank
payment evidence. Full regression: **140 passed, 243 subtests passed**, using
`/tmp/neuralclear-stripe-tests/bin/python -m pytest tests/ -q`.
No code/core/adapter changes, no commit or push, no secret-bearing output.

## What remains

This account configuration cannot complete the requested unchanged USD route.
The account owner must obtain a Stripe-supported platform/recipient corridor
for USD (with legitimate platform eligibility), or authorize a separately
specified JP/JPY flow with an explicit FX/fees/reconciliation policy. Neither
account-type switching nor waiting for pending JPY funds removes the US-region
rejection. Payout acceptance criteria are **not met**.

References: [Stripe account updates](https://docs.stripe.com/api/accounts/update),
[Connect testing](https://docs.stripe.com/connect/testing),
[country specifications](https://docs.stripe.com/api/country_specs/object).
