# Deployment

The FastAPI server on this page is a **developer sandbox**. It is not the production clearing gateway.

Production is `ClearingGateway` with `TenantHub`, on a single host, behind Caddy and Let's Encrypt. Fiat settlement is **not live**. A later move to Kubernetes would be a separate change.

- [Production runbook](production-runbook.md) — run, TLS, secrets, health, logs, backup
- [Metrics and health](metrics-health.md) — scrape endpoints and Prometheus alerts
- [Auth and tenant acceptance](acceptance-auth-tenancy.md) — operator checks for isolation

## Sandbox (Uvicorn)

```bash
python3 -m pip install -e ".[http]"
# Export NEURALCLEAR_API_KEY, NEURALCLEAR_SIGNING_SECRET, and
# NEURALCLEAR_SIGNING_KEY_ID yourself. The image and Compose file do not
# bake in a key.
NEURALCLEAR_DB=./neuralclear-sandbox.db \
uvicorn server.app:app --host 0.0.0.0 --port 8000
```

## Sandbox Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

Then open the sandbox, which is not the production gateway:

```text
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/dashboard/agents
http://127.0.0.1:8000/registry/agents
```

This is a developer sandbox, not a production finance deployment. Fiat settlement is not live. The production stack is a different file and does not start this sandbox:

```bash
docker compose -f docker-compose.production.yml up --build
```
