"""Normative escrow-v1 encoding and authentication primitives (SPEC Appendix A)."""

from __future__ import annotations

import hashlib
import hmac
import json

from .core import ProtocolError

PROFILE = "neuralclear-escrow-v1"
ZERO_HASH = "0" * 64
MAX_INTEGER = 2**53 - 1


def canonical(value) -> bytes:
    def validate(item):
        if item is None or type(item) is bool:
            return
        if type(item) is int and -MAX_INTEGER <= item <= MAX_INTEGER:
            return
        if isinstance(item, str) and all(32 <= ord(c) <= 126 for c in item):
            return
        if isinstance(item, list):
            for child in item:
                validate(child)
            return
        if isinstance(item, dict) and all(isinstance(k, str) for k in item):
            for key, child in item.items():
                validate(key)
                validate(child)
            return
        raise ProtocolError("non-canonical value (ASCII strings and safe integers only)")

    validate(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def digest(value) -> str:
    return hashlib.sha256(b"NeuralClear/meter/v1\n" + canonical(value)).hexdigest()


def authenticate(body: dict, key: bytes) -> str:
    if not isinstance(key, bytes) or not key:
        raise ProtocolError("explicit non-empty signing key required")
    return hmac.new(key, b"NeuralClear/receipt/v1\n" + canonical(body), hashlib.sha256).hexdigest()


def sign(body: dict, key: bytes, key_id: str, algorithm="HMAC-SHA256", *, domain="receipt") -> dict:
    if "signature" in body or not isinstance(key_id, str) or not key_id:
        raise ProtocolError("invalid signature envelope")
    result = dict(body, algorithm=algorithm, key_id=key_id)
    message = ("NeuralClear/" + domain + "/v1\n").encode("ascii") + canonical(result)
    if algorithm == "HMAC-SHA256":
        if not isinstance(key, bytes) or not key:
            raise ProtocolError("explicit non-empty signing key required")
        signature = hmac.new(key, message, hashlib.sha256).hexdigest()
    elif algorithm == "Ed25519":
        from .ed25519 import sign as ed_sign

        signature = ed_sign(key, message).hex()
    else:
        raise ProtocolError("unsupported algorithm")
    result["signature"] = signature
    return result


def verify_signature(envelope, keys, *, domain="receipt"):
    """keys[id] is (algorithm, key bytes); legacy raw bytes mean HMAC only."""
    try:
        trusted = keys[envelope["key_id"]]
        algorithm, key = ("HMAC-SHA256", trusted) if isinstance(trusted, bytes) else trusted
        if envelope["algorithm"] != algorithm:
            raise ProtocolError("key algorithm mismatch")
        unsigned = {k: v for k, v in envelope.items() if k != "signature"}
        message = ("NeuralClear/" + domain + "/v1\n").encode("ascii") + canonical(unsigned)
        signature = bytes.fromhex(envelope["signature"])
        if signature.hex() != envelope["signature"]:
            raise ProtocolError("non-canonical signature")
        if algorithm == "HMAC-SHA256" and isinstance(key, bytes) and key:
            valid = hmac.compare_digest(signature, hmac.new(key, message, hashlib.sha256).digest())
        elif algorithm == "Ed25519":
            from .ed25519 import verify as ed_verify

            valid = ed_verify(key, message, signature)
        else:
            raise ProtocolError("unsupported algorithm")
        if not valid:
            raise ProtocolError("signature mismatch")
        return True
    except (KeyError, ValueError, TypeError) as exc:
        raise ProtocolError("invalid signature or unknown key") from exc


def load_json(text: str):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ProtocolError("duplicate JSON member")
            result[key] = value
        return result

    try:
        value = json.loads(text, object_pairs_hook=unique)
        canonical(value)
        return value
    except (ValueError, TypeError, RecursionError) as exc:
        raise ProtocolError("invalid profile JSON") from exc
