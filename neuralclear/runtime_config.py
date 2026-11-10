"""Process configuration for the clearing gateway.

Secrets come from the environment or from a `*_FILE` path. This module
never logs secret values. Production refuses missing secrets, sandbox
defaults, and known placeholders.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEV_RECEIPT_SECRET = "dev_neuralclear_signing_secret"

_SANDBOX_ENV_VARS = (
    "NEURALCLEAR_API_KEY",
    "NEURALCLEAR_READ_API_KEY",
    "NEURALCLEAR_WRITE_API_KEY",
)

_FORBIDDEN_EXACT = {
    DEV_RECEIPT_SECRET,
    "dev_neuralclear_key",
    "dev_neuralclear_read_key",
    "changeme",
    "change-me",
    "replace-me",
    "replace-with-a-long-random-string",
    "nck_replace_me_not_a_real_key",
    "nck_example",
    "example",
    "password",
    "secret",
    "placeholder",
    "your_write_key",
}


class GatewayStartupError(RuntimeError):
    """The gateway refused to start. The message never includes secret values."""


@dataclass(frozen=True)
class GatewaySettings:
    production: bool
    host: str
    port: int
    db_path: str
    receipt_secret: str
    bootstrap_api_key: str | None
    bootstrap_tenant_name: str
    tls_mode: str
    tls_certfile: str | None
    tls_keyfile: str | None


def secret_problem(value: str | None, *, min_length: int) -> str | None:
    """Return a non-secret reason code, or None when the value is usable."""
    if value is None or value.strip() == "":
        return "missing"
    current = value.strip()
    lowered = current.lower()
    if (
        lowered in _FORBIDDEN_EXACT
        or lowered.startswith("dev_")
        or lowered.startswith("replace")
        or lowered.startswith("change")
        or "placeholder" in lowered
        or "changeme" in lowered
    ):
        return "placeholder"
    if len(current) < min_length:
        return "too_short"
    return None


def read_config_value(env: Mapping[str, str], name: str) -> str | None:
    """Read `name` or `name_FILE`. A file value wins only when it is the sole source."""
    file_name = f"{name}_FILE"
    file_path = env.get(file_name, "").strip()
    direct = env.get(name)
    direct_set = direct is not None and direct.strip() != ""
    if file_path and direct_set:
        raise GatewayStartupError(f"set only one of {name} or {file_name}")
    if file_path:
        try:
            data = Path(file_path).read_text(encoding="utf-8")
        except OSError as exc:
            raise GatewayStartupError(f"could not read {file_name}") from exc
        value = data.strip()
        return value or None
    if not direct_set or direct is None:
        return None
    return direct.strip() or None


def load_settings(env: Mapping[str, str], *, command: str) -> GatewaySettings:
    """Validate the environment for `serve`, `tenant-create`, or `tenant-rotate`."""
    mode = env.get("NEURALCLEAR_ENV", "").strip().lower()
    if mode not in {"production", "development"}:
        raise GatewayStartupError("set NEURALCLEAR_ENV to production or development")
    production = mode == "production"

    if production:
        for name in _SANDBOX_ENV_VARS:
            if env.get(name, "").strip():
                raise GatewayStartupError(
                    f"{name} is a sandbox server setting and is not accepted by the "
                    "production gateway; unset it"
                )

    db_path = env.get("NEURALCLEAR_DB", "").strip()
    if not db_path:
        raise GatewayStartupError("NEURALCLEAR_DB is required")

    receipt = read_config_value(env, "NEURALCLEAR_RECEIPT_SECRET")
    if production:
        if secret_problem(receipt, min_length=32):
            raise GatewayStartupError(
                "NEURALCLEAR_RECEIPT_SECRET is missing, too short, or still a placeholder"
            )
    elif receipt is None:
        receipt = DEV_RECEIPT_SECRET
    elif secret_problem(receipt, min_length=32):
        raise GatewayStartupError(
            "NEURALCLEAR_RECEIPT_SECRET is too short or still a placeholder"
        )
    assert receipt is not None

    bootstrap = read_config_value(env, "NEURALCLEAR_BOOTSTRAP_API_KEY")
    if bootstrap is not None and secret_problem(bootstrap, min_length=24):
        raise GatewayStartupError(
            "NEURALCLEAR_BOOTSTRAP_API_KEY is too short or still a placeholder"
        )
    tenant_name = env.get("NEURALCLEAR_BOOTSTRAP_TENANT_NAME", "").strip() or "primary"

    tls_mode = env.get("NEURALCLEAR_TLS_MODE", "terminator").strip().lower() or "terminator"
    if tls_mode not in {"terminator", "direct"}:
        raise GatewayStartupError("NEURALCLEAR_TLS_MODE must be terminator or direct")
    certfile = env.get("NEURALCLEAR_TLS_CERT_FILE", "").strip() or None
    keyfile = env.get("NEURALCLEAR_TLS_KEY_FILE", "").strip() or None
    if tls_mode == "terminator":
        certfile = None
        keyfile = None
    elif command == "serve":
        if not certfile or not keyfile:
            raise GatewayStartupError(
                "direct TLS requires NEURALCLEAR_TLS_CERT_FILE and NEURALCLEAR_TLS_KEY_FILE"
            )
        if not Path(certfile).is_file() or not Path(keyfile).is_file():
            raise GatewayStartupError("direct TLS certificate or key file is missing")

    host = env.get("NEURALCLEAR_GATEWAY_HOST", "").strip() or "127.0.0.1"
    port_raw = env.get("NEURALCLEAR_GATEWAY_PORT", "").strip() or "8080"
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise GatewayStartupError("NEURALCLEAR_GATEWAY_PORT must be an integer") from exc
    if port < 0 or port > 65535:
        raise GatewayStartupError("NEURALCLEAR_GATEWAY_PORT is out of range")

    return GatewaySettings(
        production=production,
        host=host,
        port=port,
        db_path=db_path,
        receipt_secret=receipt,
        bootstrap_api_key=bootstrap,
        bootstrap_tenant_name=tenant_name,
        tls_mode=tls_mode,
        tls_certfile=certfile,
        tls_keyfile=keyfile,
    )
