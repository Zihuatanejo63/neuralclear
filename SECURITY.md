# Security Policy

NeuralClear is a prototype and is not production ready.

Do not use this repository to custody real funds, authorize real payments, or prove real trusted execution. `MockProof` is a development placeholder only. The Stripe channel is an opt-in test-mode adapter, not a custodial, compliance, or legal-escrow control.

## Reporting Issues

Please open a private security advisory on GitHub or contact the maintainers before disclosing issues publicly.

## Known Prototype Limits

- The commercial clearing layer and legacy receipts sign with symmetric HMAC-SHA256 (shared secret). Anyone who holds the secret can forge those receipts.
- The opt-in `neuralclear-escrow-v1` profile verifies Ed25519 (pure Python, RFC 8032) on mandates, result proofs, and receipts. That implementation is not constant-time and must not protect production secrets against timing or side-channel attackers. It is not a key-management or identity system. Ed25519 on this profile does not replace HMAC on `neuralclear.clearing`.
- No real TEE attestation verification. `TEEVerifier` is an interface only.
- No ZK proof verification. `ZKVerifier` is an interface only.
- Signed protocol messages can be checked with `neuralclear.replay.ReplayStore`: unique nonce, trusted timestamp, configurable clock skew, and TTL. The seen-nonce table is SQLite and survives process restart. Task, funding, payout, and decision-id dedup still exist and are not a substitute for that nonce check. `submit_task` now requires an idempotency key, and those records expire.
- No identity recovery
- No compliance or sanctions controls
- No production-grade dispute process. Strict-profile quorum checks trust the configured signer keys and the arithmetic of the signed evidence. They do not judge service quality or detect colluding signers.
- No production custody. The first fiat path is Stripe Connect, not an in-house wallet. `neuralclear.escrow` / `neuralclear.escrow_channel` are the fiat record. `neuralclear.clearing` balances are sandbox credits (`CC`) only. There is no automatic credit-to-fiat or fiat-to-credit conversion. Internal credits are not safeguarded client funds. The Stripe adapter can talk to Stripe in test mode; it does not hold customer funds and it does not make Stripe a legal escrow. It has no card-refund method. Buyer refunds in the ledgers return internal balances only. x402 is not implemented. `StablecoinChannel` is a design-only port with no chain client, transfer, or finality logic.
- A Japan platform account transferring USD to a US connected account is an open corridor problem. Historical test-mode notes record a charge and a JPY Transfer, not a completed bank payout (`po_`). Live mode is specified in `docs/stripe-live-settlement-design.md` and is not enabled. Do not put Stripe secrets in the repo. The environment names are `STRIPE_SECRET_KEY` and, for a future webhook verifier, `STRIPE_WEBHOOK_SECRET`.

## Production baseline

The following controls are in this tree. They do **not** authorize live signing keys, live payment keys, or live webhook secrets. Live keys must not be used until a security engineer re-reviews this change.

- Production startup (`NEURALCLEAR_MODE=production`) refuses a missing or development API key, an HMAC-only receipt authenticator, the in-repo reference signer `neuralclear/ed25519.py`, and `MockProof`. The reference server still settles sandbox tasks with `MockProof`, so it fails closed in production mode and will not issue a production receipt. Escrow HTTP startup uses the same rule and requires an explicit live-environment KMS signer.
- Receipt authentication for a production configuration is Ed25519 via the `cryptography` library inside `neuralclear.kms.LocalKms` (or a future HSM adapter with the same methods). Private keys stay in the KMS object. The process verifies with public keys. Test and live key environments cannot be loaded into each other.
- Commercial receipts include `key_id` and `nonce`. Rotation is `issue_key`, `begin_overlap`, `retire_key` in `neuralclear.key_rotation` (see `docs/key-rotation-runbook.md`). Unknown and revoked kids fail. `revoke_mandate` does not revoke a signing key.
- API keys are compared with `neuralclear.secretcmp.const_equal` (SHA-256 then `hmac.compare_digest`) in `server/app.py` and `server/escrow_api.py`. There is no built-in default in the server, Dockerfile, or Compose file. `.env.example` lists variable names only.
- In production mode, reads of tasks and receipts require an API key. Sandbox reads stay open so the local preview still works.
- A future Stripe webhook, which is not implemented, must verify `Stripe-Signature`, rotate `STRIPE_WEBHOOK_SECRET` independently of the API secret, and check timestamp and replay. A callback body must not be trusted without that verification.
