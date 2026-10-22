# JP/JPY Stripe test payout attempt: 2026-10-22

## Result: blocked at platform liability acknowledgement

Checked at 2026-10-22 20:43:11 Asia/Shanghai. This is a new test-mode attempt,
not a rewrite of any previous report. No JP account, Transfer or Payout was
created. The US provider was neither retried, modified nor deleted. Internal
USD ledger state and the original signed receipt were not modified or reissued.

The former Connect activation blocker is resolved. The current blocker is a
different platform-level prerequisite: the account holder must acknowledge
connected-account loss responsibilities in the Dashboard.

## Actual creation attempts

All requests used the existing test-prefixed credential, never written here.

1. `POST /v1/accounts`: country=JP, type=custom, business_type=individual,
   capabilities[transfers][requested]=true, original internal transaction ID in
   metadata. Idempotency key `nc-jp-provider-20261022-v1`.
   HTTP 400, Request-Id `req_furDVEFFjwBWJk`. Stripe required Accounts v2 and
   identified a missing contact_email.
2. Added reserved test address `neuralclear-jp-test@example.com` to the v1
   request. Idempotency key `nc-jp-provider-20261022-v2`.
   HTTP 400, Request-Id `req_mRVnwRqJTitKta`. Stripe still required Accounts v2.
3. Followed the documented v2 creation structure:
   `POST /v2/core/accounts`, Stripe-Version `2026-09-30.endive`.
   Idempotency key `nc-jp-provider-20261022-v3`.

```json
{
  "contact_email": "neuralclear-jp-test@example.com",
  "identity": {"country": "JP"},
  "dashboard": "none",
  "defaults": {
    "responsibilities": {
      "fees_collector": "application",
      "losses_collector": "application"
    }
  },
  "configuration": {
    "recipient": {
      "capabilities": {
        "stripe_balance": {"stripe_transfers": {"requested": true}}
      }
    }
  },
  "metadata": {
    "settlement_id": "nc_stripe_test_aafa336c0da8416a9bcc34c96cae4abe"
  },
  "include": ["requirements", "configuration.recipient", "identity"]
}
```

V2 returned HTTP 400, Request-Id **`req_v2IEgGrLIHPQ6dXnm`**.
Original Stripe error fields:

```json
{
  "code": "account_creation_liability_unacknowledged",
  "doc_url": "https://dashboard.stripe.com/settings/connect/platform-profile",
  "message": "Please review the responsibilities of managing losses for connected accounts at https://dashboard.stripe.com/settings/connect/platform-profile.",
  "request_log_url": "https://dashboard.stripe.com/acct_1TQJQcE5PKlMxr4M/test/logs/req_v2IEgGrLIHPQ6dXnm"
}
```

The three keys correspond to corrected request payloads/API versions after
definitive errors, not retries of an uncertain creation. No account ID was
returned. Private allowlisted request evidence is retained in
`/private/tmp/neuralclear-stripe-live-20261022/jp-continuation.json` (0600).

## Onboarding and payout status

Official JP success bank test values were located: routing `1100000`, account
`0001234`. They were NOT submitted because creation was blocked first. No Tokyo
address, identity data or tos_acceptance was submitted. In particular, account
test terms acceptance is not the platform owner's loss-liability acknowledgement;
this run did not attempt to bypass or falsely record that acknowledgement.

| Step | Result |
| --- | --- |
| JP provider account | Not created; no acct_ ID or requirements object returned |
| JP onboarding / payouts_enabled | Not reached |
| Source-associated transfer | Not attempted; no tr_ |
| Platform-balance transfer | Not attempted; no destination account |
| Connected-account payout | Not attempted; no po_ |
| Unrelated funding | None |

No claim is made that a transfer/payout exists, is paid, or has livemode=false.
Pending-funds acceleration was not tested because the prerequisite account does
not yet exist. Do not treat the current pending charge as an available payout.

## FX 口径

- Internal settlement remains **USD 50 minor units = USD 0.50**, transaction
  `nc_stripe_test_aafa336c0da8416a9bcc34c96cae4abe`.
- Original PaymentIntent: `pi_3UTEXcE5PKlMxr4M1BLslkNm`.
- Original charge: `ch_3UTEXcE5PKlMxr4M1o0whdoo`.
- Re-fetched original balance transaction:
  `txn_3UTEXcE5PKlMxr4M15dVkqrq`, source is that exact charge.
- Stripe conversion yielded gross **JPY 79**, Stripe fee **JPY 6**, net **JPY 73**.
  API exchange_rate was `1.57715` (Stripe's amount-unit conversion field; do not
  interpret it as a JPY-per-whole-USD rate).
- Status remains `pending`; API available_on=`1793232000`.
- Intended external net settlement is **JPY 73** from that same charge, not a new
  payment. Actual external amount transferred/paid in this run is **JPY 0**.

The gross/net difference is Stripe FX and fees, not a change to the USD ledger.
No cross-currency payout was written into the USD-only ledger adapter and no new
receipt was issued. Future external evidence must be linked as FX reconciliation,
not substituted for the signed USD allocation.

## Required next action and safe continuation

The account holder must review/acknowledge the platform responsibilities at
[Connect platform profile](https://dashboard.stripe.com/settings/connect/platform-profile)
for platform `acct_1TQJQcE5PKlMxr4M` in the correct sandbox. This is the explicit
Dashboard-only stopping condition, not the obsolete Connect-not-enabled error.

After confirmation, reconcile whether any JP account exists before creating
another. Then complete its official test onboarding, attempt JPY 73 transfer
with source_transaction referencing the original charge, GET the resulting tr_,
and create/GET the JP-bank payout only when the same funds support it. Use stable
keys per payload and retain uncertain outcomes for reconciliation. No unrelated
test deposit may substitute for this pending balance.

## Verification and changes

Full regression: `/tmp/neuralclear-stripe-tests/bin/python -m pytest tests/ -q`:
**140 passed, 243 subtests passed**. No code, core.py, dependency, ledger or
receipt changes. No commit/push. Historical reports remain untouched.

Sources: [official JP bank test values](https://docs.stripe.com/connect/testing),
[Accounts v2 migration](https://docs.stripe.com/connect/accounts-v2/account-creation),
[v2 creation and liability error](https://docs.stripe.com/api/v2/core/accounts/create).
