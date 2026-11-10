from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time

from neuralclear.core import ProtocolError
from neuralclear.kms import get_process_kms
from neuralclear.production_guard import require_known_mode
from neuralclear.replay import record_replay

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
    "signed_at",
]


def result_hash(result: dict[str, object]) -> str:
    payload = json.dumps(result, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sign_receipt(receipt: dict[str, object]) -> dict[str, object]:
    signed = dict(receipt)
    signed["key_id"] = os.environ["NEURALCLEAR_SIGNING_KEY_ID"]
    signed.setdefault("nonce", secrets.token_hex(16))
    signed["signed_at"] = int(time.time())
    if require_known_mode() == "production":
        kms = get_process_kms()
        if kms is None or not getattr(kms, "persistent", False):
            raise ProtocolError("production receipts require a persistent KMS")
        message = _payload(signed)
        signature = kms.sign(str(signed["key_id"]), message, role="receipt", now=signed["signed_at"])
        signed["signature"] = "ed25519:" + signature.hex()
        record_replay(signed, "issue", "commercial-receipt")
        return signed
    signed["signature"] = _signature_for(signed)
    record_replay(signed, "issue", "commercial-receipt")
    return signed


def verify_receipt(receipt: dict[str, object]) -> bool:
    signature = receipt.get("signature")
    if not isinstance(signature, str):
        return False
    try:
        if signature.startswith("ed25519:"):
            kms = get_process_kms()
            if kms is None or not getattr(kms, "persistent", False):
                raise ProtocolError("production receipts require a persistent KMS")
            raw = bytes.fromhex(signature.split(":", 1)[1])
            now = receipt.get("signed_at")
            kms.verify(
                str(receipt["key_id"]),
                _payload(receipt),
                raw,
                now=int(now) if type(now) is int else int(time.time()),
            )
        else:
            if require_known_mode() == "production":
                raise ProtocolError("HMAC is not a production receipt authenticator")
            expected = _signature_for(receipt)
            if not hmac.compare_digest(signature, expected):
                return False
        record_replay(receipt, "verify", "commercial-receipt")
    except ProtocolError:
        raise
    except (KeyError, ValueError):
        return False
    return True


def _payload(receipt: dict[str, object]) -> bytes:
    canonical = {field: receipt[field] for field in SIGNED_RECEIPT_FIELDS}
    return json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _signature_for(receipt: dict[str, object]) -> str:
    digest = hmac.new(_secret(), _payload(receipt), hashlib.sha256).hexdigest()
    return f"hmac-sha256:{digest}"


def _secret() -> bytes:
    value = os.environ.get("NEURALCLEAR_SIGNING_SECRET", "")
    if not value:
        raise ProtocolError("NEURALCLEAR_SIGNING_SECRET is required")
    if os.environ.get("NEURALCLEAR_MODE") == "production":
        raise ProtocolError("HMAC is not a production receipt authenticator")
    return value.encode("utf-8")
