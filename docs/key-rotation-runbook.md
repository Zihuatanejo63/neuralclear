# Signing-key rotation runbook

This rotates a signing key. It does not call `revoke_mandate`. Mandate revocation and signing-key revocation are different operations.

Do not put key bytes in this file, in shell history, or in logs. The commands below use the in-process test KMS. A production HSM must expose the same steps: generate, publish the public key under a new `kid`, overlap, then revoke the old `kid`. Live keys must not be loaded until a security engineer re-reviews the production baseline.

## 1. Issue the new key

```python
from neuralclear.key_rotation import begin_overlap, issue_key, retire_key
from neuralclear.kms import LocalKms

now = 1_700_000_000  # operator clock, unix seconds
kms = LocalKms(environment="test")  # production uses environment="live" only after re-review
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
