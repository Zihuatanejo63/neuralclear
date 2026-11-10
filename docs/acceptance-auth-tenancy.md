# Acceptance checks: auth and tenant isolation

Run these against the production gateway after the stack is up. They are
the same checks as `tests/test_gateway_production.py`: a missing or wrong
key is 401, tenant A cannot read or change tenant B, rotation rejects the
old key, and health behaves.

Fiat settlement is not live. Nothing in this procedure moves customer funds
or calls Stripe. Balances are protocol credits on that tenant's ledger.

Use the public HTTPS name. Set `BASE` to it. Do not put a raw API key in
the URL, in a shell history you share, or in a ticket. The examples below
read keys from environment variables you set locally.

```bash
export BASE="https://${NEURALCLEAR_DOMAIN}"
```

`KEY_A` is the bootstrap key, read from the secret file into your shell
without printing it:

```bash
export KEY_A="$(cat "$NEURALCLEAR_BOOTSTRAP_API_KEY_FILE")"
```

## Health

These do not send a key.

```bash
curl --fail --silent "$BASE/health/live"
curl --silent --show-error --write-out '\n%{http_code}\n' "$BASE/health/ready"
```

`/health/live` is 200 and `"status":"ok"`. `/health/ready` is 200 and
`"storage":"ok"` when the volume is mounted. Both include
`"fiat_settlement":"not_live"`. A stopped database returns 503 from
`/health/ready` while `/health/live` stays 200 if the process itself is up.

`/metrics` on `$BASE` is 404 because Caddy refuses it. From the gateway
container it is 200 and contains `fiat_settlement="not_live"`:

```bash
docker compose -f docker-compose.production.yml exec gateway \
  python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080/metrics").read().decode())'
```

Confirm the text has `neuralclear_http_requests_total`,
`neuralclear_auth_failures_total`, and
`neuralclear_http_request_duration_seconds`, and that it does not contain
`KEY_A`.

## Missing and wrong keys

```bash
curl --silent --show-error --write-out '\n%{http_code}\n' "$BASE/v1/ledger"
curl --silent --show-error --write-out '\n%{http_code}\n' \
  -H 'X-NeuralClear-Api-Key: nck_not_a_real_key' \
  "$BASE/v1/ledger"
curl --silent --show-error --write-out '\n%{http_code}\n' \
  -H 'Content-Type: application/json' \
  -d '{"account":"owner.rejected","deposit":1}' \
  "$BASE/v1/accounts"
```

Each response is HTTP 401 and `{"error":"invalid api key"}`. The missing
key is rejected on reads as well as writes. The wrong key does not return
a ledger.

## Two tenants

Create tenant B. Copy the printed `api_key` into `KEY_B` in your shell, then
clear the terminal scrollback if you share the session. The command prints
the key once; the database stores only a hash.

```bash
docker compose -f docker-compose.production.yml exec gateway \
  python -m neuralclear.gateway tenant-create --name "Tenant B"
export KEY_B='paste-the-issued-key-only-in-your-shell'
```

Open an account as A and as B.

```bash
curl --fail --silent -X POST "$BASE/v1/accounts" \
  -H "X-NeuralClear-Api-Key: $KEY_A" -H 'Content-Type: application/json' \
  -d '{"account":"owner.a","deposit":50}'
curl --fail --silent -X POST "$BASE/v1/accounts" \
  -H "X-NeuralClear-Api-Key: $KEY_B" -H 'Content-Type: application/json' \
  -d '{"account":"owner.b","deposit":7}'
```

Read both ledgers:

```bash
curl --fail --silent -H "X-NeuralClear-Api-Key: $KEY_A" "$BASE/v1/ledger"
curl --fail --silent -H "X-NeuralClear-Api-Key: $KEY_B" "$BASE/v1/ledger"
```

A's body contains `owner.a` with balance 50 and does not contain `owner.b`.
B's body contains `owner.b` with balance 7 and does not contain `owner.a`.

Open a channel and settle it as A, after opening the provider account:

```bash
curl --fail --silent -X POST "$BASE/v1/accounts" \
  -H "X-NeuralClear-Api-Key: $KEY_A" -H 'Content-Type: application/json' \
  -d '{"account":"agent.a","deposit":0}'
CHANNEL=$(curl --fail --silent -X POST "$BASE/v1/channels" \
  -H "X-NeuralClear-Api-Key: $KEY_A" -H 'Content-Type: application/json' \
  -d '{"buyer":"owner.a","provider":"agent.a","deposit":20}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["channel_id"])')
curl --silent --show-error --write-out '\n%{http_code}\n' -X POST \
  "$BASE/v1/channels/${CHANNEL}/meter" \
  -H "X-NeuralClear-Api-Key: $KEY_B" -H 'Content-Type: application/json' \
  -d '{"capability":"echo","amount":1,"payload_hash":"sha256:nope"}'
```

B's meter is HTTP 400. A's ledger is unchanged by that call. A can still
meter and settle the same channel:

```bash
curl --fail --silent -X POST "$BASE/v1/channels/${CHANNEL}/meter" \
  -H "X-NeuralClear-Api-Key: $KEY_A" -H 'Content-Type: application/json' \
  -d '{"capability":"echo","amount":1,"payload_hash":"sha256:ok"}'
RECEIPT=$(curl --fail --silent -X POST "$BASE/v1/channels/${CHANNEL}/settle" \
  -H "X-NeuralClear-Api-Key: $KEY_A" -H 'Content-Type: application/json' \
  -d '{}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["receipt_id"])')
curl --fail --silent -H "X-NeuralClear-Api-Key: $KEY_A" "$BASE/v1/receipts/${RECEIPT}"
curl --silent --show-error --write-out '\n%{http_code}\n' \
  -H "X-NeuralClear-Api-Key: $KEY_B" "$BASE/v1/receipts/${RECEIPT}"
```

A receives the receipt. B receives HTTP 404. B cannot mutate A's account
list: a deposit from B creates an account only on B's ledger.

## Rotation

Rotate A's key. The command prints the new key once. The previous key must
then fail for reads and writes.

```bash
docker compose -f docker-compose.production.yml exec gateway \
  python -m neuralclear.gateway tenant-rotate --tenant-id "$TENANT_A_ID"
export KEY_A_NEW='paste-the-new-key-only-in-your-shell'
curl --silent --show-error --write-out '\n%{http_code}\n' \
  -H "X-NeuralClear-Api-Key: $KEY_A" "$BASE/v1/ledger"
curl --fail --silent -H "X-NeuralClear-Api-Key: $KEY_A_NEW" "$BASE/v1/ledger"
```

The old key is 401. The new key returns A's ledger, including `owner.a`,
and still does not return B's accounts. Restart is not required. The
gateway reads the current key hash from SQLite on each request.

## Production signer, replay, and MockProof

These checks apply when `NEURALCLEAR_MODE=production`. Fiat settlement is still not live. Do not set `NEURALCLEAR_KMS_ENV=live` and do not load a live signing key. The in-tree KMS is a test-environment file, not an HSM.

`POST /v1/clear` against a provider that returns `MockProof` is HTTP 400, the body contains `MockProof is not allowed in production`, and the buyer's protocol-credit balance is unchanged after the refund.

A channel settlement receipt has `signature` starting with `ed25519:` and a `key_id`. Verifying that receipt a second time fails with `replayed nonce`. After `retire_key` on that `kid`, verification fails with `revoked key`. The old tenant API key is a separate rotation; retiring a signing kid does not by itself revoke API keys.

Unset the shell variables when you are done:

```bash
unset KEY_A KEY_B KEY_A_NEW
```
