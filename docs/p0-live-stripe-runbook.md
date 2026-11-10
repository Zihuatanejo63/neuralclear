# P0 Stripe test-mode runbook

## Status: blocked before any Stripe API call

Checked on 2026-10-22, in this order:

1. STRIPE_SECRET_KEY in the execution environment: no usable test-key candidate.
2. Repository .env.local: no usable test-key candidate.
3. ~/.config/neuralclear/stripe.env: no usable test-key candidate.

No sk_test_ credential was available. No Stripe API requests, account creation,
browser sign-in, PaymentIntent, transfer or payout occurred. There are no Stripe
object IDs to report. No live-run result document or executable live-run script
has been created: the requested missing-key stop condition applies.
The existing escrow_channel_demo.py remains explicitly fake HTTP, not a Stripe run.

## What the owner must provide

Using the Stripe account you report creating in April 2026, open its Dashboard
yourself, select test mode/the intended sandbox, and obtain the test secret API key.
Provide it locally as STRIPE_SECRET_KEY in the environment or in one of the two
files above. Do not paste it into chat, source, documentation, command history or
test output. A publishable key or live secret key is not acceptable. Local key files
should be readable only by your OS user (mode 600).

.gitignore now excludes .env.local and stripe.env in addition to .env. The home
configuration file is outside this repository; do not copy it into a tracked file.
Before any future commit, run git check-ignore on the actual secret file and verify
it is not already tracked. Ignore rules do not untrack previously committed secrets.

Only the test key is needed to resume the initial API preflight. Completing payout
also depends on an authorized Connect provider account, its test external bank
account and available test balance. These are account prerequisites, not extra
secrets. Do not invent an acct_ ID or assume the platform's own account is a provider.
If none exists, report that blocker and ask the owner to select/configure one;
do not silently create an account or switch to live mode.

## Execution checklist after the key is available

1. Read the same three sources in order without printing values. Reject anything
   other than a nonempty sk_test_ key. Never fall back to live credentials. Use a
   new run ID and persist it for retries; no random replacement idempotency keys
   after an uncertain network outcome.
2. Use real StripeHTTP (default urllib opener), not FakeStripeHTTP. Check account
   access, the selected connected account's destination configuration and balances.
   Restrict requests to api.stripe.com. Confirm livemode=false on payment objects.
   Retrieve credentials only into memory; redact Authorization and client_secret.
3. Create a durable ClearingLedger in usd with an independently protected
   FileCheckpoint, trusted owner/provider signing keys and the selected provider
   account mapping. Generate signing seeds securely; do not reuse the example's
   public demonstration seed. Keep private seeds outside evidence exports/repo.
4. Prepare a signed mandate and transaction through the SDK escrow profile. Use
   integer cents. The USD charge minimum is 50 cents; a 50-cent service plus a
   5-cent fee gives a 55-cent charge, matching the existing demo. Check account
   currency/minimum constraints before creating it. A successful 55-cent charge
   does NOT guarantee enough available balance for a 50-cent transfer after Stripe
   fees, settlement delay and reserves. Report insufficiency rather than inventing
   money, topping up automatically or silently increasing the charge.
5. Call StripeChannel.create_deposit with Funding and the persistent deposit key.
   Record the returned pi_ ID only. Its metadata must retain buyer, escrow_id and
   funding_key; StripeChannel.confirm_deposit validates these exact bindings.
6. Attach/confirm with Stripe's pm_card_visa test PaymentMethod (the 4242 Visa test
   scenario), not raw card data. StripeChannel.confirm_deposit does NOT confirm a
   card: use the real PaymentIntent confirmation API first. Ensure card-compatible
   payment settings; automatic methods that require redirects may require a
   return_url or disabling redirects. Use a stable confirmation idempotency key.
   If additional action or account restrictions block success, record the actual
   status/error and stop funding, rather than marking it succeeded locally.
7. Re-fetch the PaymentIntent through StripeChannel.confirm_deposit. Only actual
   succeeded state with the exact received amount and currency may credit escrow.
   Verify a duplicate confirmation does not increase supply or held funds again.
8. Execute mandate checks, hash-chain metering and net settlement through the
   existing escrow workflow. Return a signed result; settle 50 cents and 5 cents
   fee for the normal branch. This work is local protocol processing, not a claim
   that Stripe verified service quality.
9. Call StripeChannel.payout for the finalized transaction. This performs two real
   steps: platform transfer to the selected connected account (tr_), then payout
   from that connected account (po_, using Stripe-Account). Record each returned ID.
   A transfer is NOT a bank payout. Capture the tr_ ID immediately, even if the
   subsequent payout fails. The current adapter does not expose every intermediate
   object on failure; the future live runner should wrap real HTTP with sanitized
   response recording, without substituting responses or modifying core behavior.
10. If payout is pending/in_transit, report that exact state and use authenticated
    retrieval/reconcile_payout later. Do not report paid early. Keep reservations
    on failure/unknown outcome. Reconcile existing objects; do not blindly repeat
    POSTs after a crash or bypass the ledger's repeat-payout rejection.
11. Generate the signed clearing receipt and export the meter chain and PUBLIC key.
    Run the independent verifier (no Ledger instance is required):

```sh
python -m neuralclear.verify /path/to/receipt.json /path/to/chain.json \
  --algorithm Ed25519 --key-id clearing --key-file /path/to/public.key
```

If payout is blocked but internal settlement completed, independently verify the
clearing receipt anyway, clearly labeling the external payout incomplete. Receipt
validity proves internal allocation/signature consistency, not a bank transfer.
Stripe test-mode transactions themselves do not move real money.

## Required results record

After an actual attempt, create docs/p0-live-stripe-run-2026-10-22.md (or use the
actual run date if later). Record steps separately:

| Step | Real/local | Object ID | Status | Evidence |
| --- | --- | --- | --- | --- |
| PaymentIntent creation and confirmation | Real Stripe API | Actual pi_ | Actual status | Re-fetch, livemode=false |
| Escrow, mandate, metering, net settlement | Local protocol | Transaction ID | Actual state | Journal/checkpoint |
| Connected-account transfer | Real Stripe API | Actual tr_ if created | Actual result | Retrieve in same test environment |
| Bank payout | Real Stripe API | Actual po_ if created | Actual status | Account-scoped retrieval |
| Signed receipt and offline verification | Local protocol | Receipt transaction/revision | VALID or failure | CLI exit code |

Use 'not created' for absent objects, never invented example IDs. Preserve only
sanitized error type/code, HTTP status and safe explanatory text; exclude secrets,
Authorization, client_secret, payment/card/bank details and full response dumps.
Every reported Stripe ID must be retrievable in that account's test Dashboard/API.
Describe the precise account or balance prerequisite for any blocked step.

## Official references

- [Stripe testing and test PaymentMethods](https://docs.stripe.com/testing)
- [PaymentIntent creation and minimum amounts](https://docs.stripe.com/api/payment_intents/create)
- [PaymentIntent confirmation](https://docs.stripe.com/api/payment_intents/confirm)
- [Connect testing and payouts](https://docs.stripe.com/connect/testing)

Consult these again when executing; test-account capabilities and available balances
must be checked live rather than inferred from this checklist.
