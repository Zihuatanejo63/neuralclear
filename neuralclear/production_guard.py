"""Fail closed before production startup.

Live signing keys must not be used until a security engineer re-reviews this
tree. These checks only refuse known-bad startup. They do not authorize live keys.
"""

from __future__ import annotations

import os

from .core import ProtocolError

DEV_MATERIAL = frozenset(
    {
        "dev_neuralclear_key",
        "dev_neuralclear_read_key",
        "dev_neuralclear_signing_secret",
        "ed25519:demo",
        "test-api-key",
        "test-read-key",
        "test-signing-secret",
    }
)


def assert_operator_secret(value: object, label: str) -> None:
    if not isinstance(value, str) or not value or value in DEV_MATERIAL or value.startswith("dev_neuralclear"):
        raise ProtocolError(f"{label} is missing or is a development default")


def assert_production_signer(signer: object) -> None:
    if signer is None:
        raise ProtocolError("production requires an explicit KMS signer")
    module = getattr(signer, "__module__", "") or getattr(signer, "__name__", "")
    if (
        module == "neuralclear.ed25519"
        or getattr(signer, "reference_implementation", False)
        or getattr(signer, "REFERENCE_IMPLEMENTATION", False)
    ):
        raise ProtocolError("reference Ed25519 signer is not allowed in production")
    algorithm = getattr(signer, "algorithm", None)
    if algorithm != "Ed25519":
        raise ProtocolError("HMAC is not a production receipt authenticator")
    if getattr(signer, "environment", None) != "live":
        raise ProtocolError("production KMS must be the live environment")


def assert_production_proof(proof_name: str) -> None:
    if proof_name == "MockProof":
        raise ProtocolError("MockProof is not allowed in production")


def assert_replay_store_configured() -> None:
    if not os.environ.get("NEURALCLEAR_REPLAY_STORE"):
        raise ProtocolError("production requires NEURALCLEAR_REPLAY_STORE")


def assert_reference_server_ready(*, api_keys: list[str], signer: object, proof_name: str) -> None:
    if not api_keys:
        raise ProtocolError("API key is missing or is a development default")
    for index, key in enumerate(api_keys):
        assert_operator_secret(key, f"API key {index}")
    assert_production_signer(signer)
    assert_production_proof(proof_name)
    assert_replay_store_configured()


def assert_escrow_app_ready(*, write_key: object, signer: object, algorithm: str) -> None:
    assert_operator_secret(write_key if isinstance(write_key, str) else "", "write API key")
    if algorithm != "Ed25519":
        raise ProtocolError("HMAC is not a production receipt authenticator")
    assert_production_signer(signer)
    assert_production_proof("SIGNED_RESULT")
    assert_replay_store_configured()
