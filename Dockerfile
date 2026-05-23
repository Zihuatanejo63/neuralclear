FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY client ./client
COPY examples ./examples
COPY neuralclear ./neuralclear
COPY server ./server

RUN python -m pip install --no-cache-dir -e ".[http]"

ENV NEURALCLEAR_DB=/data/neuralclear.db
ENV NEURALCLEAR_API_KEY=dev_neuralclear_key

EXPOSE 8000

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
