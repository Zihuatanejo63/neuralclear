# Receipts

Receipts record settled sandbox transactions.

A receipt includes:

- `receipt_id`
- `transaction_id`
- `quote_id`
- `sender`
- `receiver`
- `amount`
- `fee`
- `state`
- `created_at`

Receipts are persisted when `NEURALCLEAR_DB` points to a SQLite database.
