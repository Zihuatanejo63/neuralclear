# Production gateway runbook

This is the single-host Docker Compose deployment of `ClearingGateway`.
Caddy terminates TLS with Let's Encrypt and proxies HTTP to the gateway on
the Compose network. A later migration to Kubernetes would be a separate
change. Do not add a cluster manifest to this deployment.

## What is not live

**Fiat settlement is not live.** This gateway is not wired to Stripe, Stripe
Connect, `escrow`, or `escrow_channel`. It does not custody customer funds
and it does not hold fiat balances.

Clearing balances are protocol credits (`CC`) for the clearing protocol.
They are not bank deposits, not legal escrow, and not a balance a customer
can withdraw as money. A later fiat path, if one is built, uses Stripe
Connect with `escrow` / `escrow_channel` as the source of truth. That path
is intentionally absent from this process.

The FastAPI app in `server.app` is a developer sandbox. The production
Compose file does not start it.

## What you need on the host

- Docker Engine and the Compose plugin.
- A DNS name whose A/AAAA records point at this host before the stack starts.
- TCP 80 and 443 reachable from the public internet so Let's Encrypt can
  complete the HTTP-01 challenge. UDP 443 is published for HTTP/3.
- Secret files that live outside the git checkout. Do not commit them.

The gateway container listens on `8080` inside the Compose network only.
Do not publish `8080`, the Caddy admin port, or the Caddy metrics port.

## Secret files

Create the files on the host. The commands generate values into those files.
They do not print a key into this document, and the gateway stores only a
hash of each API key.

```bash
umask 077
sudo mkdir -p /var/lib/neuralclear/secrets
sudo python3 -c 'import secrets; open("/var/lib/neuralclear/secrets/receipt_secret","w").write(secrets.token_urlsafe(48))'
sudo python3 -c 'import secrets; open("/var/lib/neuralclear/secrets/bootstrap_api_key","w").write("nck_"+secrets.token_hex(32))'
sudo chmod 600 /var/lib/neuralclear/secrets/receipt_secret /var/lib/neuralclear/secrets/bootstrap_api_key
```

Export paths and the public name. Use your own DNS name and contact address.
`gateway.example.com` and `ops@example.com` are placeholders and will not
obtain a certificate.

```bash
export NEURALCLEAR_DOMAIN=gateway.example.com
export NEURALCLEAR_ACME_EMAIL=ops@example.com
export NEURALCLEAR_ACME_CA=https://acme-v02.api.letsencrypt.org/directory
export NEURALCLEAR_RECEIPT_SECRET_FILE=/var/lib/neuralclear/secrets/receipt_secret
export NEURALCLEAR_BOOTSTRAP_API_KEY_FILE=/var/lib/neuralclear/secrets/bootstrap_api_key
export NEURALCLEAR_BOOTSTRAP_TENANT_NAME=primary
```

For a first rehearsal, point `NEURALCLEAR_ACME_CA` at the Let's Encrypt
staging directory so a mistake does not hit production rate limits:

```text
https://acme-staging-v02.api.letsencrypt.org/directory
```

Switch it back to the production directory before real traffic. Staging
certificates are not trusted by browsers. The `caddy-data` volume remembers
the account, so change directories only with that in mind.

The process rejects empty values, the sandbox key `dev_neuralclear_key`, the
dev receipt secret, and the placeholders in `.env.example`. Production also
refuses to start if `NEURALCLEAR_API_KEY` is set: that variable belongs to
the sandbox, not this gateway.

`NEURALCLEAR_RECEIPT_SECRET` signs protocol receipts. Set it before the first
settlement and keep the same value across restarts. Receipts already signed
with another secret will not verify. The value is never written to the
database or to request logs.

The bootstrap file creates the first tenant when the database has no matching
key. Later starts with the same file reuse that tenant. They do not print
the key. Keep the file if you still want that key to work. Additional
tenants are issued with `tenant-create`, which prints a new key once on that
command's stdout.

## Run

From the repository directory, with the variables above exported:

```bash
docker compose -f docker-compose.production.yml up --build -d
docker compose -f docker-compose.production.yml ps
```

Compose will refuse to start if `NEURALCLEAR_DOMAIN`, `NEURALCLEAR_ACME_EMAIL`,
or either secret-file path is missing. The gateway process then refuses to
serve if the secret file is empty, still a placeholder, or if no tenant
exists.

Readiness:

```bash
docker compose -f docker-compose.production.yml exec gateway \
  python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080/health/ready").read().decode())'
```

Public HTTPS, after DNS and issuance succeed:

```bash
curl --fail "https://${NEURALCLEAR_DOMAIN}/health/live"
```

`/health/live` only checks that the process is answering. `/health/ready`
and `/health` also run `SELECT 1` against the SQLite file and return 503
when storage is down. Both bodies include `"fiat_settlement": "not_live"`.

Prometheus is bound to `127.0.0.1:9090` on the host. Alerts are visible at
`http://127.0.0.1:9090/alerts`. Nothing in this stack sends them to a
webhook. Add a notifier outside the repository if you need pages, and do
not commit its credentials.

## TLS

The supported shape is HTTP behind Caddy. `NEURALCLEAR_TLS_MODE=terminator`
is set in the Compose file, so the gateway does not load a certificate.

Caddy reads `deploy/Caddyfile`:

- Port 80 answers the ACME HTTP-01 challenge and redirects other traffic to HTTPS.
- Port 443 presents the Let's Encrypt certificate for `NEURALCLEAR_DOMAIN`.
- The public name proxies to `gateway:8080`, except `/metrics`, which is
  answered with 404 at the edge.
- Caddy metrics listen on `:9080` inside the Compose network only.
- The admin API is off.

Certificates and the ACME account live in the `caddy-data` volume. Renewal
is automatic, about 30 days before expiry. The blackbox exporter checks the
certificate Caddy presents, using the public name as SNI and as the HTTP
Host header, while connecting to the `caddy` service. Alerts fire if that
probe fails for 15 minutes, if remaining life drops under 21 days, or if
expiry stops being reported. Details are in [metrics-health.md](metrics-health.md).

Optional direct TLS, without Caddy, is a different shape. Set
`NEURALCLEAR_TLS_MODE=direct` and point `NEURALCLEAR_TLS_CERT_FILE` and
`NEURALCLEAR_TLS_KEY_FILE` at files mounted into the gateway container.
The process exits if either file is missing. Do not commit those files.
The Compose file in this repository does not use direct TLS.

## Logs

Gateway access logs are JSON lines on stdout: time, method, path without
the query string, route template, status, duration, tenant id, and request
id. They do not include API keys, the receipt secret, or request bodies.
Caddy deletes the `X-NeuralClear-Api-Key` header from its access log and
redacts `nck_` tokens in the URI. Send the key only in that header, never
in the URL.

```bash
docker compose -f docker-compose.production.yml logs -f gateway
docker compose -f docker-compose.production.yml logs -f caddy
```

Docker's json-file driver keeps five files of 20 MB per service. Ship those
container logs with whatever agent you already run on the host. Do not turn
on header dumps or a debug proxy that records `X-NeuralClear-Api-Key`.

`tenant-create` and `tenant-rotate` print a new API key on the stdout of
that command. That is the issuance record, not a request log. Do not copy it
into a ticket or a log pipeline. Store it in a secret manager.

## Backup and restore

Two volumes matter:

- `neuralclear-production_gateway-data` holds `neuralclear-gateway.db`
  (tenant hashes, protocol-credit ledgers, receipts, channels).
- `neuralclear-production_caddy-data` holds the Let's Encrypt account and
  certificates. Losing it forces a new issuance and can hit rate limits.

Take a consistent SQLite copy while the gateway is running:

```bash
docker compose -f docker-compose.production.yml exec -T gateway \
  python -c 'import sqlite3; s=sqlite3.connect("/data/neuralclear-gateway.db"); d=sqlite3.connect("/data/neuralclear-gateway.backup"); s.backup(d); d.close(); s.close()'
mkdir -p backups
docker compose -f docker-compose.production.yml cp \
  gateway:/data/neuralclear-gateway.backup \
  ./backups/neuralclear-gateway.db
```

Copy the Caddy volume while the stack is stopped, or with a filesystem
snapshot of the Docker volume. Example with the stack stopped:

```bash
docker compose -f docker-compose.production.yml stop
docker run --rm \
  -v neuralclear-production_gateway-data:/data:ro \
  -v neuralclear-production_caddy-data:/caddy:ro \
  -v "$PWD/backups":/backups \
  alpine:3 \
  sh -c 'cp /data/neuralclear-gateway.db /backups/neuralclear-gateway.db && tar -C /caddy -czf /backups/caddy-data.tgz .'
docker compose -f docker-compose.production.yml start
```

Restore the gateway database only while the gateway container is stopped,
then start it again. Restoring a copy over a running SQLite file will
corrupt it.

```bash
docker compose -f docker-compose.production.yml stop gateway
docker run --rm \
  -v neuralclear-production_gateway-data:/data \
  -v "$PWD/backups":/backups:ro \
  alpine:3 \
  cp /backups/neuralclear-gateway.db /data/neuralclear-gateway.db
docker compose -f docker-compose.production.yml start gateway
```

To restore Caddy state, stop `caddy`, unpack `caddy-data.tgz` into the
`caddy-data` volume, and start `caddy` again. Confirm
`https://${NEURALCLEAR_DOMAIN}/health/live` and the TLS probe before
deleting the previous backup.

Backups contain hashed API keys and protocol-credit state. They do not
contain raw API keys or the receipt secret. Treat them as private
operational data anyway. They are not a fiat ledger.

## Tenant keys

Issue another tenant. The new key appears once on stdout:

```bash
docker compose -f docker-compose.production.yml exec gateway \
  python -m neuralclear.gateway tenant-create --name "Example Tenant"
```

Rotate a key. The old key stops working as soon as the command commits,
including for ledger and receipt reads:

```bash
docker compose -f docker-compose.production.yml exec gateway \
  python -m neuralclear.gateway tenant-rotate --tenant-id ten_example
```

The running process reads the key hash from SQLite on each request, so a
rotation from this command invalidates the previous key without a restart.
The ledger for that tenant is left in place.

Operator checks for auth and isolation are in
[acceptance-auth-tenancy.md](acceptance-auth-tenancy.md).
