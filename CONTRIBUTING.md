# Contributing

Thanks for improving NeuralClear.

This repository is intentionally small. Please keep changes focused on protocol clarity, executable examples, and tests for settlement behavior.

## Development

```bash
python3 examples/demo.py
python3 examples/marketplace/demo_marketplace.py
python3 -m unittest discover
```

## Guidelines

- Keep protocol objects serializable to JSON.
- Add tests for every financial or clearing change.
- Do not represent mock proofs as real TEE, ZK, or cryptographic verification.
- Keep resource metering separate from settlement credit.
- Preserve the invariant that positive transaction amount means sender pays receiver.
