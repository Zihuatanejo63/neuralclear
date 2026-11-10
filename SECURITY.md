# Security Policy

NeuralClear is a prototype and is not production ready.

Do not use this repository to custody real funds, authorize real payments, or prove real trusted execution. `MockProof` is a development placeholder only. The Stripe channel is an opt-in test-mode adapter, not a custodial, compliance, or legal-escrow control.

## Reporting Issues

Please open a private security advisory on GitHub or contact the maintainers before disclosing issues publicly.

## Known Prototype Limits

- Sandbox commercial receipts sign with symmetric HMAC-SHA256 (shared secret). Anyone who holds the secret can forge those receipts. Production commercial receipts are Ed25519 from `PersistentKms` (`cryptography`); HMAC is refused on that path.
- Sandbox `neuralclear-escrow-v1` can still verify Ed25519 with the pure-Python reference in `neuralclear/ed25519.py`. That implementation is not constant-time. Production issue and verify refuse it and refuse HMAC unless a persistent KMS signer is passed. The pure-Python module is not a key-management system. Live signing keys must not be placed in `PersistentKms` or any other in-tree adapter.
- No real TEE attestation verification. `TEEVerifier` is an interface only.
- No ZK proof verification. `ZKVerifier` is an interface only.
- Issue and verify of commercial receipts, HMAC result proofs, and escrow-v1 mandate, result, receipt, and decision envelopes call `ReplayStore.admit`. In production, an envelope without a nonce and an integer `signed_at` fails closed instead of skipping the store. Production opens `NEURALCLEAR_REPLAY_STORE`. The default clock skew is 30 seconds and the default nonce TTL is 24 hours, which is longer than the skew on purpose: skew is how far a new message's timestamp may drift, and the TTL is how long a consumed nonce is remembered so it cannot be replayed. A 30-second TTL would be too short for that memory. Re-reading a stored receipt is not the same as accepting the signed message again. A replay rolls the SQLite transaction back. Task, funding, payout, and decision-id dedup still exist and are not a substitute. `submit_task` requires an idempotency key, and those records expire.
- No identity recovery
- No compliance or sanctions controls
- No production-grade dispute process. Strict-profile quorum checks trust the configured signer keys and the arithmetic of the signed evidence. They do not judge service quality or detect colluding signers.
- No production custody. The first fiat path is Stripe Connect, not an in-house wallet. `neuralclear.escrow` / `neuralclear.escrow_channel` are the fiat record. `neuralclear.clearing` balances are sandbox credits (`CC`) only. There is no automatic credit-to-fiat or fiat-to-credit conversion. Internal credits are not safeguarded client funds. The Stripe adapter can talk to Stripe in test mode; it does not hold customer funds and it does not make Stripe a legal escrow. It has no card-refund method. Buyer refunds in the ledgers return internal balances only. x402 is not implemented. `StablecoinChannel` is a design-only port with no chain client, transfer, or finality logic.
- A Japan platform account transferring USD to a US connected account is an open corridor problem. Historical test-mode notes record a charge and a JPY Transfer, not a completed bank payout (`po_`). Live mode is specified in `docs/stripe-live-settlement-design.md` and is not enabled. Do not put Stripe secrets in the repo. The environment names are `STRIPE_SECRET_KEY` and, for a future webhook verifier, `STRIPE_WEBHOOK_SECRET`.

## Production baseline

The following controls are in this tree. They do **not** authorize live signing keys, live payment keys, or live webhook secrets. Live keys must not be used until a security engineer re-reviews this change.

- Production startup (`NEURALCLEAR_MODE=production`) calls `install_persistent_kms`, refuses a missing or development API key on each request as well as at startup, refuses an unknown mode, and refuses HMAC, a raw `receipt_key`, `neuralclear/ed25519.py`, and `LocalKms` on the sign and verify paths themselves. `NEURALCLEAR_KMS_ENV` is read and must match the adapter environment. The in-tree adapter rejects `live`. The reference server's sandbox task runner can still attach `MockProof` as an execution placeholder; that is not a production attestation and it is not the authentication control.
- Production issue and verify for escrow-v1 (`wire.sign`, `wire.verify_signature`, `EscrowLedger.receipt`, `issue_mandate`, result proofs) and commercial receipts (`server.signing.sign_receipt` / `verify_receipt`) call `PersistentKms`, which uses `cryptography` and stores keys in SQLite. `LocalKms` is test-only and is rejected as a production signer, including `LocalKms(environment="live")`. `PersistentKms` is not a certified HSM. Live signing keys must not be placed in it.
- Commercial receipts include `key_id` and `nonce`. Rotation is `issue_key`, `begin_overlap`, `retire_key` in `neuralclear.key_rotation` (see `docs/key-rotation-runbook.md`). Unknown and revoked kids fail. `revoke_mandate` does not revoke a signing key.
- API keys are compared with `neuralclear.secretcmp.const_equal` (SHA-256 then `hmac.compare_digest`) in `server/app.py` and `server/escrow_api.py`. There is no built-in default in the server, Dockerfile, or Compose file. `.env.example` lists variable names only.
- In production mode, reads of tasks, receipts, settlements, and balances require an API key, as do the dashboard routes that show receipts, transactions, balances, or disputes. Sandbox reads stay open so the local preview still works. Registry agent listing does not expose those records and stays unauthenticated.
- `PersistentKms` stores private key bytes in a local SQLite file. That is not an HSM and not a KMS service. Live signing keys remain forbidden until a later security verdict replaces this adapter with an operator HSM.
- A future Stripe webhook, which is not implemented, must verify `Stripe-Signature`, rotate `STRIPE_WEBHOOK_SECRET` independently of the API secret, and check timestamp and replay. A callback body must not be trusted without that verification.
