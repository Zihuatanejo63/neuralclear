# Metrics and health

The production process is the clearing gateway behind Caddy on one host.
Prometheus in `docker-compose.production.yml` scrapes it and evaluates
`deploy/prometheus/alerts.yml`. No Alertmanager receiver is configured, and
this repository has no webhook secret. Fiat settlement is not live; the
info metric says so.

A later Kubernetes migration would be a separate change. These names are
for the Compose jobs, not for a cluster.

## Endpoints

| Endpoint | Auth | Meaning |
| --- | --- | --- |
| `GET /health/live` | none | Process is answering. Does not check SQLite. |
| `GET /health/ready` | none | Process can serve, and SQLite answers `SELECT 1` when storage is configured. |
| `GET /health` | none | Same check as `/health/ready`. |
| `GET /metrics` | none | Prometheus text. Not exposed on the public Caddy name. |

Readiness returns 200 with `"storage": "ok"` or 503 with `"storage": "error"`.
Every health body includes `"fiat_settlement": "not_live"`.

On the Compose network:

- Gateway metrics: `http://gateway:8080/metrics`
- Gateway health: `http://gateway:8080/health/ready`
- Caddy metrics: `http://caddy:9080/metrics`
- Public HTTPS health: `https://<your-domain>/health/live` and `/health/ready`
- Public `https://<your-domain>/metrics` is forced to 404

Prometheus itself is published only as `127.0.0.1:9090` on the host.

Do not put an API key in a scrape URL. Metrics are unauthenticated on the
Compose network because they contain no keys. Keep port 8080 and port 9080
unpublished.

## Series

`neuralclear_gateway_up` is 1 when the process can render metrics.
Prometheus' own `up{job="neuralclear-gateway"}` is 0 when the scrape fails,
which is the process-down signal.

`neuralclear_gateway_ready` is 1 only when the readiness check passes.

`neuralclear_gateway_info{version="0.4.0.dev0",fiat_settlement="not_live"}` is 1.

`neuralclear_http_requests_total{method,route,status,tenant_id}` counts
requests. `route` is a template such as `/v1/receipts/{id}`, not the raw
id. `tenant_id` is the tenant id, `legacy` for the single-key demo, `none`
for health and metrics, or `anonymous` when authentication failed. It is
never an API key.

`neuralclear_auth_failures_total{reason}` counts `missing` and `invalid`
keys. The HTTP body for both is `401` and `{"error":"invalid api key"}`.

`neuralclear_http_request_duration_seconds` is a histogram by `method` and
`route` only, so tenant cardinality stays on the counter.

`probe_success{job="neuralclear-tls"}` and
`probe_ssl_earliest_cert_expiry{job="neuralclear-tls"}` come from the
blackbox exporter. The probe connects to `https://caddy/health/live` with
SNI and Host set to the public DNS name, which is the certificate Caddy
serves for Let's Encrypt.

`up{job="neuralclear-edge"}` is the Caddy process scrape.

## Alert rules

The file `deploy/prometheus/alerts.yml` is loaded by the Compose Prometheus.
The expressions below are that file.

Process down:

```text
up{job="neuralclear-gateway"} == 0
```

for 2 minutes. The edge has the same shape on `job="neuralclear-edge"`.

Not ready, while the process is still scraped:

```text
(sum(neuralclear_gateway_ready) == 0) and (sum(up{job="neuralclear-gateway"}) == 1)
```

for 5 minutes.

High 5xx: at least five 5xx responses in 10 minutes, and more than 5% of
requests in that window, sustained for 5 minutes.

```text
sum(increase(neuralclear_http_requests_total{status=~"5.."}[10m])) >= 5
and
sum(increase(neuralclear_http_requests_total{status=~"5.."}[10m]))
  / clamp_min(sum(increase(neuralclear_http_requests_total[10m])), 1) > 0.05
```

Auth-failure spike: at least 20 missing or invalid keys in 10 minutes,
sustained for 5 minutes.

```text
sum(increase(neuralclear_auth_failures_total[10m])) >= 20
```

Certificate renewal and expiry, from the blackbox probe of the certificate
Caddy is presenting:

```text
probe_success{job="neuralclear-tls"} == 0
```

for 15 minutes, and

```text
(probe_ssl_earliest_cert_expiry{job="neuralclear-tls"} - time()) < 21 * 24 * 3600
```

for 30 minutes. Let's Encrypt certificates are renewed by Caddy about 30
days before expiry. Life under 21 days means that renewal is not succeeding.
Keep the `caddy-data` volume. An `absent(...)` rule fires when the probe has
not reported an expiry for 30 minutes, which also covers a probe that never
came up after a restart.

Open `http://127.0.0.1:9090/alerts` on the host to see what is firing.
Wiring those alerts to a pager is an operator choice and is not part of
this repository.
