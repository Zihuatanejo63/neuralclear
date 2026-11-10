from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets

from neuralclear.core import ProtocolError

SIGNED_RECEIPT_FIELDS = [
    "receipt_id",
    "transaction_id",
    "buyer",
    "provider",
    "amount",
    "fee",
    "currency",
    "timestamp",
    "result_hash",
    "key_id",
    "nonce",
]


def result_hash(result: dict[str, object]) -> str:
    payload = json.dumps(result, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sign_receipt(receipt: dict[str, object]) -> dict[str, object]:
    if os.environ.get("NEURALCLEAR_MODE") == "production":
        raise ProtocolError("use the KMS Ed25519 signer in production")
    signed = dict(receipt)
    signed["key_id"] = os.environ["NEURALCLEAR_SIGNING_KEY_ID"]
    signed.setdefault("nonce", secrets.token_hex(16))
    signed["signature"] = _signature_for(signed)
    return signed


def verify_receipt(receipt: dict[str, object]) -> bool:
    signature = receipt.get("signature")
    if not isinstance(signature, str):
        return False
    try:
        expected = _signature_for(receipt)
    except (KeyError, ProtocolError):
        return False
    return hmac.compare_digest(signature, expected)


def _signature_for(receipt: dict[str, object]) -> str:
    canonical = {field: receipt[field] for field in SIGNED_RECEIPT_FIELDS}
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    digest = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"hmac-sha256:{digest}"


def _secret() -> bytes:
    value = os.environ.get("NEURALCLEAR_SIGNING_SECRET", "")
    if not value:
        raise ProtocolError("NEURALCLEAR_SIGNING_SECRET is required")
    if os.environ.get("NEURALCLEAR_MODE") == "production":
        raise ProtocolError("HMAC is not a production receipt authenticator")
    return value.encode("utf-8")
