# Disputes

The sandbox supports opening a dispute for an existing transaction:

```text
POST /neuralclear/disputes
```

Disputes are state records only. The prototype does not implement arbitration, evidence review, automatic refund policy, slashing policy, or legal claims.

Production deployments must define how disputes are resolved and who can trigger refunds or slashing.
