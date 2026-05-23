from __future__ import annotations

import hashlib
import hmac
import json
import os

DEFAULT_SIGNING_SECRET = "dev_neuralclear_signing_secret"

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
]


def result_hash(result: dict[str, object]) -> str:
    payload = json.dumps(result, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sign_receipt(receipt: dict[str, object]) -> dict[str, object]:
    signed = dict(receipt)
    signed["signature"] = _signature_for(signed)
    return signed


def verify_receipt(receipt: dict[str, object]) -> bool:
    signature = receipt.get("signature")
    if not isinstance(signature, str):
        return False
    try:
        expected = _signature_for(receipt)
    except KeyError:
        return False
    return hmac.compare_digest(signature, expected)


def _signature_for(receipt: dict[str, object]) -> str:
    canonical = {field: receipt[field] for field in SIGNED_RECEIPT_FIELDS}
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    digest = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"hmac-sha256:{digest}"


def _secret() -> bytes:
    return os.environ.get("NEURALCLEAR_SIGNING_SECRET", DEFAULT_SIGNING_SECRET).encode("utf-8")
