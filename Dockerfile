FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY client ./client
COPY examples ./examples
COPY neuralclear ./neuralclear
COPY server ./server

RUN python -m pip install --no-cache-dir -e ".[http]"

# No API keys, signing secrets, or certificates are baked into this image.
# The default command is the developer sandbox. Production Compose overrides
# it with `python -m neuralclear.gateway serve` and injects secrets at runtime.
ENV NEURALCLEAR_DB=/data/neuralclear.db
ENV NEURALCLEAR_MODE=sandbox

EXPOSE 8000 8080

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
