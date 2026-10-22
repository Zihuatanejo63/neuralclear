# JP/JPY continuation: Transfer complete, Payout awaiting available balance

Observed: 2026-10-22 21:06:03 Asia/Shanghai. All remote operations used test-mode
credentials. Historical reports, US account, internal USD ledger and receipt
were left unchanged. No unrelated funding was created.

## Account reconciliation and onboarding

Before creation, v1 accounts list returned only `acct_1UTL2zE5PK2LWR96` (US),
has_more=false. The v2 list returned the same single ID, next_page_url=null.
No JP account existed. The new v2 request used the previously specified
recipient/stripe_transfers configuration, dashboard=none, application fee/loss
responsibility, reserved test email, and settlement_id metadata.
Idempotency key: `nc-jp-provider-20261022-v4`.

Created JP provider **`acct_1UTLeyE5PKAPsCly`**, v2 livemode=false. It is an
application-managed/no-dashboard recipient (Custom-equivalent responsibilities),
not a platform account. The v1 compatibility response reports type=none; this
report does not falsely label that field as custom.

Compatible v1 updates completed its requirements:
- Individual test identity with kana/kanji names, Tokyo/Shibuya/Jingumae example
  address and postal code 1500001. These are illustrative test details, not a
  claim of a verified real person or an official fixed address fixture.
- Official success DOB 1902-01-01 and `file_identity_document_success` token.
- Software-services MCC 5734, test service description, project website.
- Test terms acceptance timestamp and loopback IP 127.0.0.1, API accepted.
- Official JP successful bank test values: routing 1100000/account 0001234.

Bank ID: **`ba_1UTLg5E5PKAPsClylUgrIuJ5`**, JPY, initial bank status=new.
Update keys: `nc-jp-onboard-20261022-v1`, `nc-jp-document-20261022-v1`,
`nc-jp-bank-20261022-v1`.

Final GET: transfers=active, payouts_enabled=true, currently_due=[],
past_due=[], pending_verification=[], disabled_reason=null.
No manual identity or new platform-liability acknowledgement was fabricated.

## Transfer: real success, original charge associated

`POST /v1/transfers`:
- amount=73, currency=jpy
- destination=`acct_1UTLeyE5PKAPsCly`
- source_transaction=`ch_3UTEXcE5PKlMxr4M1o0whdoo`
- metadata[settlement_id]=`nc_stripe_test_aafa336c0da8416a9bcc34c96cae4abe`
- Idempotency-Key: `nc-transfer-aafa336c-jp-v2`

Created **`tr_3UTEXcE5PKlMxr4M1dCS9D9S`**. A subsequent GET of that exact
Transfer confirmed amount=73, currency=jpy, livemode=false, reversed=false,
the same source_transaction and the intended JP destination. Transfer objects
do not have a payout-style paid status; successful creation is not bank payment.
No platform-balance fallback was necessary or attempted.

Destination payment: `py_1UTLgNE5PKAPsClyYZgB0IQU`.
Platform transfer balance transaction: `txn_3UTEXcE5PKlMxr4M14tVp07r`.
Provider balance transaction: **`txn_1UTLgOE5PKAPsClyeBzYf3n0`**, source is
that destination payment; amount/net=73, fee=0, currency=jpy, status=pending.

## Payout: real request rejected for pending funds

`POST /v1/payouts`, Stripe-Account=`acct_1UTLeyE5PKAPsCly`:
- amount=73, currency=jpy
- destination=`ba_1UTLg5E5PKAPsClylUgrIuJ5`
- same settlement_id metadata
- Idempotency-Key: `nc-payout-aafa336c-jp-v1`

HTTP **400**, Request-Id **`req_gfmYixkrgXnQVa`**. Original error:

```json
{
  "type": "invalid_request_error",
  "code": "balance_insufficient",
  "message": "You have insufficient funds in your Stripe account for this transfer. Your card balance is too low.  You can use the /v1/balance endpoint to view your Stripe balance (for more details, see stripe.com/docs/api#balance)."
}
```

No po_ was created, so no payout GET or livemode claim is possible.
Provider balance GET: livemode=false, available JPY 0, pending JPY 73.
Provider balance-transaction available_on=**1793232000**, i.e.
**2026-10-29 08:00 Asia/Shanghai** (00:00 UTC).

Official test documentation offers special cards that bypass pending balance
when a payment is created. It does not document retroactively applying those
cards to this succeeded payment. Test clocks are for attached test-clock objects,
not an identified mechanism to accelerate this existing Connect transfer.
No supported same-transaction acceleration was found; no speculative mutation,
replacement charge, unrelated top-up or fake payout was attempted.

## FX 口径

Internal settlement remains **USD 50 minor units (USD 0.50)**. Original charge
conversion was **JPY 79 gross - JPY 6 Stripe fee = JPY 73 net**, evidenced by
`txn_3UTEXcE5PKlMxr4M15dVkqrq` in the earlier run.
External Transfer now actually moved **JPY 73** of that charge's proceeds into
the JP provider's pending balance. Actual bank payout so far: **JPY 0**.
Destination transfer fee was zero, so its net remains JPY 73.
No USD-to-JPY relabeling occurred inside the ledger and no receipt was reissued.
This is external FX reconciliation evidence, not a new USD ledger allocation.

## Safe continuation and acceptance

After available_on, GET the provider balance, original Transfer and payout list
first (including automatic payouts, if any). Only if no payout already consumed
these funds and JPY 73 is available should the same intended payout be retried.
Do not create another Transfer. Reconcile idempotency retention and prior outcome
before any POST; do not blindly retry across days. A future po_ must be GET-checked
for amount, currency, livemode=false and actual status, never assumed paid.

Acceptance: JP account and tr_ confirmed; po_ **not yet achieved**. The completed
Transfer is preserved and not reversed. No future retry was scheduled by this run.

## Tests and evidence

`/tmp/neuralclear-stripe-tests/bin/python -m pytest tests/ -q`:
**140 passed, 243 subtests passed**.
No code/core.py/dependency changes; no commit or push. The public companion JSON
contains IDs, amounts, currencies, statuses/mode flags and timestamps only.
Private allowlisted history: `/private/tmp/neuralclear-stripe-live-20261022/jp-continuation-v4.json`.

References: [Connect test fixtures](https://docs.stripe.com/connect/testing),
[available-balance test cards](https://docs.stripe.com/testing#available-balance),
[payout requirements](https://docs.stripe.com/api/payouts/create),
[test clocks](https://docs.stripe.com/api/test_clocks).
