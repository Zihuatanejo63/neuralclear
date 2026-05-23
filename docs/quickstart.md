# Quickstart

NeuralClear is a prototype sandbox for agent service clearing. It uses internal test credits and does not execute real payments.

## Install

```bash
python3 -m pip install -e ".[http]"
```

## Run The Server

```bash
NEURALCLEAR_API_KEY=dev_neuralclear_key \
NEURALCLEAR_DB=./neuralclear-sandbox.db \
uvicorn server.app:app --port 8000
```

Open:

```text
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/dashboard/agents
```

## Use The CLI

```bash
export NEURALCLEAR_BASE_URL=http://127.0.0.1:8000
export NEURALCLEAR_API_KEY=dev_neuralclear_key

python3 -m client.cli agents list
python3 -m client.cli agents search summarize.pdf
python3 -m client.cli quote request agent.pdf_summarizer summarize.pdf
```

Use the returned `quote_id`:

```bash
python3 -m client.cli task submit quote_xxx --text "Summarize this PDF text."
python3 -m client.cli receipts list
python3 -m client.cli balances
```
