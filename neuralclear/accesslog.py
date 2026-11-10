"""JSON access logs for the clearing gateway.

Request lines go to stdout. API keys and other secret-shaped fields are dropped.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import TextIO

_KEY_RE = re.compile(r"nck_[A-Za-z0-9_-]+")
_SENSITIVE = ("api_key", "apikey", "authorization", "secret", "password", "token", "credential")


def scrub(value: object) -> object:
    if isinstance(value, str):
        return _KEY_RE.sub("[redacted]", value)
    if isinstance(value, dict):
        cleaned: dict[str, object] = {}
        for key, item in value.items():
            if _sensitive_name(str(key)):
                continue
            cleaned[str(key)] = scrub(item)
        return cleaned
    if isinstance(value, list):
        return [scrub(item) for item in value]
    return value


def _sensitive_name(name: str) -> bool:
    lowered = name.lower()
    return any(part in lowered for part in _SENSITIVE)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": scrub(record.getMessage()),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            scrubbed = scrub(fields)
            if isinstance(scrubbed, dict):
                payload.update(scrubbed)
        return json.dumps(payload, default=str)


def configure_access_log(stream: TextIO | None = None) -> logging.Logger:
    logger = logging.getLogger("neuralclear.gateway")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not any(getattr(handler, "_neuralclear_access", False) for handler in logger.handlers):
        handler = logging.StreamHandler(stream or sys.stdout)
        handler.setFormatter(JsonFormatter())
        handler._neuralclear_access = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    return logger
