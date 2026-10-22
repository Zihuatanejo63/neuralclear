# Protocol gap audit

Audit date: 2026-10-21. Baseline: current working tree before this task.
Statuses below describe the baseline, not promises inferred from class names.
Existing uncommitted website, docs and Stripe adapter files are excluded from edits.

## SPEC section comparison

| Section | Baseline status | Evidence and interoperability impact |
| --- | --- | --- |
| 0 Scope | 部分实现 | Local service clearing exists; no escrow, meter chain or interoperable clearing profile. Stripe channel is an unconnected port, not a ledger implementation. |
| 1 Roles | 部分实现 | core.AgentRegistry, SDK and reference service model roles; no authenticated owner/provider identity binding. |
| 2 Objects | 与 SPEC 不一致 | SPEC calls receipts future/in-memory; server.models.Receipt and SQLiteStorage implement them. Core and HTTP manifest representations differ; no normative receipt wire encoding. |
| 3 Direction | 已实现 | Ledger.settle debits amount+fee, credits receiver and fee_pool. Numeric type/currency isolation is not enforced by Ledger; annotate as a validation gap. |
| 4 Metering | 部分实现 | ResourceUnit and SettlementCredit separated; resource usage is an estimate copied by SDK. No incremental evidence/hash chain, rate binding or netting. |
| 5 Manifest | 部分实现 | Schema, examples and registry exist. AgentInfo.to_json uses capability objects/reputation_score; registry accepts capability strings/pricing/reputation. Third-party discovery cannot assume one encoding. |
| 6 Mandates | 部分实现 | Expiry, capability, per-task and daily checks exist. No revocation, total budget reservation, real signature check or approval enforcement; SDK does not bind sender to owner. |
| 7 Lifecycle | 部分实现 | Transaction.transition matches the diagram and rejects invalid pairs. Ledger.settle bypasses transitions by assigning SETTLED, even from wrong states; refund/dispute only change state. |
| 8 Proof | 部分实现 | MockProof only accepts NONE/mock-signature. SignedResultProof, ReproducibleProof, TEEAttestationProof, ZKProof raise NotImplementedError. server.signing HMAC receipts are real MAC checks, not public attestation. |
| 9 Disputes | 仅文档未实现 | Diagram exists; Ledger.refund never moves balances. open_dispute stores a separate dispute record and does not even transition the transaction; no freeze, arbitrator policy, partial releases or refunds. SPEC explicitly disclaims escrow. |
| 10 Zero sum | 部分实现 | Exact aggregate and per-transaction delta helpers exist. Settlement calls aggregate check only; no independently specified clearing evidence, escrow accounting or signed conservation statement. |
| 11 Errors | 与 SPEC 不一致 | HTTP generally emits 400 with free-text detail, conflict 409; no stable SPEC error code envelope. |
| 12 Discovery | 部分实现 | GET well-known, quote/task/receipt routes and urllib client exist; no wire-version negotiation, canonical JSON rules or negotiated profile. app/version versions also differ. OpenAPI documents task/dispute 202 but app returns 200; receipt schema has nested credits while HTTP uses integers. |
| 13 Security | 与 SPEC 不一致 | HMAC receipts and persisted task idempotency now exist despite blanket disclaimers. Development secrets and mock proofs remain; no public-key trust model. |
| 14 Non-goals | 已实现 | Prototype has no custody/payment licensing claims; a payment adapter does not make the ledger production finance. |

## Prioritized gaps and disposition

| ID | Priority / reason | Required work | Disposition |
| --- | --- | --- | --- |
| G1 | P0: prevent invalid money movements | Strict opt-in escrow state machine, freeze, settlement, partial dispute award and refund; all edges tested | Implemented in neuralclear/escrow.py; tests/test_escrow.py covers all 121 state pairs plus monetary invariants. Legacy core/HTTP behavior intentionally retained. |
| G2 | P0: independent verification is impossible without bytes/rules | Versioned canonical encoding, meter hash chain, full-receipt MAC, exact conservation checks and CLI | Implemented in wire.py / verify.py and SPEC Appendix A; independent of Ledger instances. tests/test_verify.py includes every-field tampering, reordering/truncation, invalid signed arithmetic and CLI exit codes. |
| G3 | P0: cross-language implementations need stable oracles | Checked-in positive/negative JSON vectors with expected results | Implemented: tests/fixtures/escrow_v1.json, 5 positive and 5 negative vectors; tests/test_protocol_vectors.py replays input and compares frozen outputs, plus independent hashlib/hmac calculations. |
| G4 | P1: crash recovery / tamper evidence | Append-only ledger persistence, verified replay, trusted head/checkpoint for truncation detection | Implemented: journal.py + optional EscrowLedger persistence; full-chain validation before replay, exact external checkpoint comparison, POSIX writer lock, fsync, fail-closed crash handling. FileCheckpoint supports a separately protected checkpoint file. Tests cover replay, every truncation/event tamper, invalid operation rollback, checkpoint failure and durable anchor recreation. |
| G5 | P1 (overlaps G2): distinguish mock from real verification | Explicit algorithm/key ID, real signature validation and documented trust | Implemented: stdlib Ed25519 plus HMAC, key-to-algorithm binding, result-domain signatures, public-key receipt CLI verification. RFC 8032 section 7.1 tests 1-3 pass; malformed/malleable signatures rejected. Legacy Proof classes untouched. TEE/ZK remain explicitly unimplemented interfaces, as requested. |
| G6 | P1: enforce delegated authority | Signed identity-bound mandates, revocation, atomic budget reservation/decrement and approval | Implemented: owner-bound signature verification, expiry/revocation checks on execution and metering, journaled revocations/reservations, fee-inclusive per-task/daily/total limits, serialized atomic reservation and partial-settlement consumption. Human threshold fails closed; owner must issue revised signed authority. |
| G7 | P2: network interoperability | Wire version negotiation, stable errors, cross-process verifier example | Implemented as opt-in server/escrow_api.py app factory, leaving server.app unchanged; explicit profile/version headers, stable section 11 codes and additional version/auth errors. End-to-end example exports receipts checked in an independent verifier process. Limited trusted-operator transport, not a multi-tenant public API. |
| G8 | P0 documentation: avoid inventing guarantees | SPEC opt-in profile with exact wire semantics and limitations; no silent reinterpretation of legacy SDK | Implemented in SPEC Appendix A. Explains exact bytes, key trust, funding/refund equations, state semantics, freshness and limitations. |

## Verification record

Stage 1 baseline: 74 passed under Python 3.13.1 in the temporary pytest environment.
The first sandboxed run could not bind the existing process E2E server; the same
suite passed with local port permission. Both requested --ignore flags were used;
the Python 3.9 collection errors were neither repaired nor counted as passing.

Incremental checks: G1 first passed 6 tests / 126 subtests; G2 passed 9 tests /
44 subtests; G3 passed 1 test / 10 fixture subtests. Final suite: **92 passed**
(Python 3.13.1, 2026-10-21), including 18 new tests and the existing Stripe stub
tests. Command:

```sh
/tmp/neuralclear-stripe-tests/bin/python -m pytest tests/ \
  --ignore=tests/test_idempotency.py \
  --ignore=tests/test_openapi_consistency.py
```

The final G1 suite also covers repeated dispute cycles and defensive snapshots.
No new third-party core dependency was added; core.py, sdk.py, server/, client/
and pyproject.toml retain their prior behavior/content.

## G4-G7 follow-up verification (2026-10-22)

Incremental full pytest runs on Python 3.13.1:

| Milestone | Result |
| --- | --- |
| G4 persistence | 97 passed (two pre-existing collection-error files ignored) |
| G5 Ed25519 | 100 passed (same ignores) |
| G6 mandates | 105 passed (same ignores) |
| G7 HTTP and collection diagnosis | 113 passed, no ignores |
| Integration plus negative-path checks | 122 passed, no ignores |

Commands use `/tmp/neuralclear-stripe-tests/bin/python -m pytest tests/`;
the temporary environment supplies pytest and HTTP extras, not core dependencies.
Existing localhost process tests require port permission. Core dependencies remain
empty; no crypto library was introduced. The new example and both old demos run.

The two required E2E branches in tests/test_escrow_channel_e2e.py pass **2/2**:

- test_normal_funding_metering_payout_and_independent_verification
- test_dispute_partial_award_refund_and_independent_verification

Both use actual StripeChannel/StripeHTTP with an injected urllib opener (no network),
Ed25519 signed mandate/result/receipt, journal replay, and a subprocess running
`python -m neuralclear.verify` with PUBLIC key bytes only. Normal allocation: deposit
55, provider 50, fee 5, refund 0. Partial dispute: deposit 55, provider 20, fee 2,
refund 33. Paid payout removes the provider allocation from outstanding supply,
leaving respectively 5 and 35 internally. Receipt conservation describes allocation
before the separate external withdrawal, not fabricated bank settlement evidence.
An additional test checks pending-payout restart, non-tradable reserved funds and
exactly-once paid reconciliation.

SDK selection: `NeuralClearSDK(registry, ledger, profile="neuralclear-escrow-v1").escrow()`.
It returns the prepare/execute workflow; default legacy call remains unchanged.
`ClearingLedger` supplies the concrete ledger-owned Stripe channel boundary.
No hidden conversion or copying between legacy CC balances and fiat ledgers occurs.

### Python 3.9.6 collection diagnosis

Reproduced directly with `/usr/bin/python3` (3.9.6):

1. tests/test_idempotency.py line 18 evaluated `dict[str, object] | None` at import,
   raising TypeError. Added only `from __future__ import annotations`; semantics
   unchanged. Import and all four tests now pass on 3.9.6.
2. tests/test_openapi_consistency.py imports server.app. In this 3.9 environment
   FastAPI is absent, so server.app's ImportError branch sets Header=None; the
   default expression `Header(default=None)` at line 64 then raises TypeError.
   This is an existing optional-dependency guard bug in production code, NOT the
   test. Per instructions it is not modified. Suggested separate fix: define the
   Header-dependent functions only when FastAPI is available. Project metadata
   requires Python >=3.10; installing supported HTTP extras is the normal runtime.

The system 3.9 environment has no pytest. A direct unittest run of idempotency,
Ed25519, journal, signed-mandate and channel E2E modules passed 24 tests, including
pending-payout restart/reconciliation. Full pytest (including both formerly
ignored modules) passes under the supported 3.13 HTTP-equipped environment.

## Remaining boundaries

This is an opt-in internal-credit protocol profile, not an upgrade of existing
HTTP routes or SDK defaults. HMAC recipients can independently implement checks
but can also forge them; Ed25519 public-key verification is now available.
Receipts prove an authenticated, internally consistent transaction statement, not
global solvency, resource truth or that this is the latest revision. A trusted
checkpoint is required to detect rollback/omission of whole valid receipts.
Post-settlement dispute freeze fails if provider funds are no longer available;
withdrawal collateral/window policy remains application work.

G4-G7 are no longer deferred within the requested reference scope. Remaining
deployment work is explicit: protect checkpoints against rollback independently,
provision owner/provider keys and resolve uncertain external Stripe outcomes.
The pure Python signer is not constant-time; use a hardened implementation before
production secret handling. Refunds in this demo return internal credits, not card
refunds. TEE/ZK, real usage truth, automatic arbitration, public multi-tenant auth,
chargebacks and production payment operations are not claimed implemented.
The original Stripe adapter and legacy core/API stay unchanged; a new concrete
ClearingLedger bridges the existing port. Existing website/docs/launch changes
are preserved. No commit/push.
This profile nets metered usage within one transaction; multilateral or multi-task
batch netting is not specified or implemented in this iteration.

## Gemini 独立评估回应（2026-10-22）

This section supersedes earlier automatic-arbitration/single-writer statements
only for the new opt-in policies. Legacy defaults remain unchanged.

| Finding | Disposition | Evidence and remaining boundary |
| --- | --- | --- |
| Hard issue 1: custody/compliance | 部分解决 (claims only); production capability 诚实延后 | README, SPEC, WHITEPAPER now align on clearing semantics + adapters; licensed partners must provide custody/compliance. docs/custody-boundaries.md records three design routes, explicitly not discovered historical text or existing contracts. No KYC/AML implementation. |
| Hard issue 2: formal-only disputes | 部分解决 | StrictEscrowLedger: frozen-chain seq/hash evidence, deterministic no-delivery refunds and partial metered awards, Ed25519 k-of-n distinct keys, revision/decision-ID replay protection. test_empty_delivery_refunds_and_partial_delivery_releases and test_quorum_evidence_and_bypass_rejected. Does not judge truth or quality; signatures still trust signers. |
| Hard issue 3: empty proof support | 部分解决 | Strict signed-delivery-only metering fails closed for mock/TEE/ZK. test_mock_and_unimplemented_proofs_fail_closed. Merkle module plus verify_meter_inclusion; test_merkle_authenticated_inclusion_and_tampering. TEE/ZK execution proofs remain unimplemented, not replaced by Merkle. |
| Missing a: distributed durable backend | 部分解决 locally; distributed P2 诚实延后 | Optional wait_for_writer holds POSIX lock for recovery + whole ledger session; no stale-state append. test_serialized_writers_preserve_chain_and_budget runs 8 processes, asserts 20 unique events, valid recovery and only one 55-credit reservation. No replication/HA/network filesystem guarantees; external database/backend needed. |
| Missing b: real TEE/ZK integration | 诚实延后 | Requires selected attestation platform/proof system, verifier dependencies, trusted roots and independent security review. Only interfaces ship. Ed25519 and Merkle prove authentication/integrity, not execution. |
| Missing c: compliant payment/stablecoin rail | 部分解决 guard; payout 诚实延后 | Read-only conservative Connect preflight and guarded creation helper, fake-opener tests in test_connect_preflight.py. Empty account list is UNKNOWN, not definitive disabled/enabled; explicit operator confirmation for fresh platforms. Existing payout blocker unchanged, no creation retried. StablecoinChannel is Protocol only. |

### Usage and security boundary

Instantiate `neuralclear.strict_escrow.StrictEscrowLedger` explicitly with trusted
arbitrator and per-provider public keys. Use `meter_verified`, then freeze with
`transition(..., "DISPUTED")`, create `decision`, collect signatures in domain
`decision`, and `resolve`. Default EscrowLedger, legacy SDK and HTTP semantics are
unchanged. Existing workflow's raw meter path intentionally fails on this strict
ledger; applications must use the explicit signed-delivery entry point.

Full signed decisions are available separately through `decision_record`; old
receipt wire fields remain compatible. Independent Merkle verification first
authenticates the full chain against the receipt; a compact signed Merkle-root
receipt extension remains future work. No claim of independent execution truth.

No Stripe credentials were read, no Connect account was created, and no historical
payout report was altered in this iteration. No commit/push.

### Verification for this iteration

- Strict-policy initial checkpoint: 4 tests passed.
- Offline Connect preflight + multiprocess journal checkpoint: 4 tests passed.
- Final complete suite: `python -m pytest tests/ -q`, **140 passed,
  243 subtests passed** using `/tmp/neuralclear-stripe-tests/bin/python`.
- Added restart/replay regression:
  `test_signed_decision_survives_restart_and_rejects_replay`.
- Added distinct-public-key regression: `test_key_alias_cannot_inflate_quorum`.
- `git diff --check`: passed. No dependencies added.
- Merkle CLI: append `--inclusion-entry entry.json --inclusion-proof proof.json`
  to the existing receipt/chain verifier command. Both inputs are required
  together; signature/root/entry mismatch fails closed.
