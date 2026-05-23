# Mandates

`SpendingMandate` grants a buyer agent bounded authority to spend on behalf of an owner.

It includes:

- `owner`
- `agent`
- `allowed_capabilities`
- `max_per_task`
- `max_daily`
- `valid_until`
- `requires_human_approval_above`
- `signature`

The prototype checks expiration, capability, currency, per-task budget, and daily budget. It does not verify real cryptographic signatures.
