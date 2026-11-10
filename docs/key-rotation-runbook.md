# Signing-key rotation runbook

This rotates a signing key. It does not call `revoke_mandate`. Mandate revocation and signing-key revocation are different operations.

Do not put key bytes in this file, in shell history, or in logs. The commands below use the in-process test KMS. A production HSM must expose the same steps: generate, publish the public key under a new `kid`, overlap, then revoke the old `kid`. Live keys must not be loaded until a security engineer re-reviews the production baseline.

## 1. Issue the new key

```python
from neuralclear.key_rotation import begin_overlap, issue_key, retire_key
from neuralclear.kms import LocalKms

now = 1_700_000_000  # operator clock, unix seconds
kms = LocalKms(environment="test")  # tests only; production calls install_persistent_kms
# Do not label test key material as live. The in-tree adapter rejects environment "live".
issue_key(kms, purpose="receipt", kid="receipt-2026-a", now=now, roles={"receipt"})
issue_key(kms, purpose="receipt", kid="receipt-2026-b", now=now, roles={"receipt"})
```

Use a distinct `purpose` of `mandate` and role `mandate` for escrow-v1 mandate keys. Commercial receipts and escrow-v1 envelopes both select the key by `key_id` / `kid`.

## 2. Dual-key window

```python
begin_overlap(kms, "receipt-2026-a", now=now, overlap_seconds=7 * 24 * 3600)
```

Until `not_after`, both kids verify. Sign new messages with `receipt-2026-b`. Keep accepting `receipt-2026-a` on messages whose timestamp falls inside the window.

## 3. Retire the old key

```python
retire_key(kms, "receipt-2026-a")
```

Verification of `receipt-2026-a` now fails with `revoked key`, including messages that previously verified. `receipt-2026-b` still verifies. An unknown kid fails with `unknown key`.

## 4. Reject after revoke

Confirm with a verify call before deleting any public-key record. Do not delete the revoked public key until operators have finished investigating in-flight messages. Deletion is not required for rejection; `revoked` is sufficient.

## Replay window

`ReplayStore` defaults are a 30-second clock skew and a 24-hour nonce TTL. The TTL is longer than the skew on purpose. Skew is only how far a newly presented timestamp may sit from the verifier's clock. The TTL is how long that nonce stays remembered so the same signed message cannot be accepted again. A 30-second TTL would forget the nonce quickly enough to allow a replay of a long-lived receipt. Receipts themselves remain stored records; the replay store is not their retention policy.
