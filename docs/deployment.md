# Deployment

The reference server can run directly with Uvicorn or through Docker Compose.

## Uvicorn

```bash
python3 -m pip install -e ".[http]"
NEURALCLEAR_API_KEY=dev_neuralclear_key \
NEURALCLEAR_DB=./neuralclear-sandbox.db \
uvicorn server.app:app --host 0.0.0.0 --port 8000
```

## Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

Then open:

```text
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/dashboard/agents
http://127.0.0.1:8000/registry/agents
```

This is a developer sandbox, not a production finance deployment.
