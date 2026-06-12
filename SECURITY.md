# Security Policy

NeuralClear is a prototype and is not production ready.

Do not use this repository to custody real funds, authorize real payments, or prove real trusted execution. `MockProof` is a development placeholder only.

## Reporting Issues

Please open a private security advisory on GitHub or contact the maintainers before disclosing issues publicly.

## Known Prototype Limits

- Signatures are symmetric HMAC-SHA256 only (shared secret); no asymmetric / public-key (ed25519) verification yet
- No real TEE attestation verification
- No ZK proof verification
- Replay protection is limited to idempotency keys on task submission; no nonce-based protection on proofs or protocol messages
- No identity recovery
- No compliance or sanctions controls
- No production-grade dispute process
