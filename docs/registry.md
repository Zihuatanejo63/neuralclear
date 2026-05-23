# Registry

The sandbox registry stores agent manifests and supports capability search.

Seed manifests live in:

```text
examples/agents/
```

The default seed agents are:

- `agent.pdf_summarizer` with `summarize.pdf`
- `agent.web_search` with `search.web`
- `agent.code_review` with `review.code`

Register an additional agent:

```bash
python3 -m client.cli agent register examples/well-known/agent.json
```

Search by capability:

```bash
python3 -m client.cli agents search summarize.pdf
```
