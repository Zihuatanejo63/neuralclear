# Custody and compliance boundaries

NeuralClear is a clearing-semantics engine plus channel adapters. Custody and
compliance must be performed by licensed partners. Reserved internal credits
are not legal escrow, safeguarded client funds, deposit insurance or bank finality.
KYC/AML, sanctions screening, licensing, cross-border eligibility and safeguarding
are not implemented. Deployment requires jurisdiction-specific professional review.

## Three design routes, none implemented as custody here

The requested earlier three-route design was not found in this checkout. The
following records design options explicitly, not a claim of an existing partner
contract or regulatory approval:

1. Licensed escrow/custody partner holds funds; NeuralClear sends release intents
   and reconciles signed partner statements. Disputes require an enforceable
   partner release/refund policy, including insolvency and chargeback treatment.
2. Licensed marketplace payment partner manages connected providers and funds
   flows. Stripe Connect is a potential channel, not automatically legal escrow.
   Account onboarding, country/currency compatibility and external payout must
   be proven independently. Current platform Connect activation is blocked.
3. Licensed stablecoin custody/payment partner manages wallets, identity checks,
   redemption and chain-finality risk. A token contract alone is not compliance.
   `neuralclear/stablecoin_channel.py` is only a port specification, no adapter.

## Present evidence and limits

The Stripe test collection/internal clearing evidence remains valid, but external
payout is NOT complete. Preserve the conclusions in
[payout attempt](p0-live-stripe-payout-2026-10-22.md). No new Stripe network call
was made for this hardening iteration. Only the account owner can resolve the
documented Connect activation blocker.

Strict disputes validate signed evidence references and deterministic arithmetic.
They do not detect a colluding provider/arbitrator or evaluate semantic quality.
Merkle inclusion proves membership under an authenticated root, not truthful work.
TEE/ZK have no implementation. POSIX journal locking serializes local processes;
a multi-instance distributed database, replication and failover remain P2.

Stripe API documents [account listing](https://docs.stripe.com/api/accounts/list)
as a list operation, not a definitive platform activation probe. The conservative
preflight refuses an empty unconfirmed platform; operator confirmation is not an
API attestation and cannot override an actual creation failure.
