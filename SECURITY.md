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
- Legacy task submission replay protection is idempotency keys. Escrow-v1 rejects reused funding and payout idempotency keys and replayed strict-profile decisions. There is still no general nonce on every protocol message, and the commercial HMAC proof path has no nonce.
- No identity recovery
- No compliance or sanctions controls
- No production-grade dispute process. Strict-profile quorum checks trust the configured signer keys and the arithmetic of the signed evidence. They do not judge service quality or detect colluding signers.
- No production custody. Internal credits and escrow balances are protocol state, not safeguarded client funds. The Stripe adapter can talk to Stripe in test mode; it does not hold customer funds and it does not make Stripe a legal escrow. x402 is not implemented. `StablecoinChannel` is a design-only port with no chain client, transfer, or finality logic.
