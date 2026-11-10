"""Production receipt signer for the clearing gateway.

Signs with the process PersistentKms (Ed25519, test environment only) and
records the nonce in ReplayStore. HMAC is not used. Live keys are not accepted.
"""

from __future__ import annotations

import json
import secrets
import time

from .core import ProtocolError
from .replay import record_replay


def _message(receipt: dict[str, object]) -> bytes:
    body = {key: value for key, value in receipt.items() if key != "signature"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


class KmsReceiptSigner:
    """Ed25519 receipt signer. ``kms`` must be a persistent test-environment KMS."""

    def __init__(self, kms: object, kid: str) -> None:
        self.kms = kms
        self.kid = kid

    def sign(self, receipt: dict[str, object]) -> dict[str, object]:
        signed = dict(receipt)
        signed["key_id"] = self.kid
        signed["nonce"] = secrets.token_hex(16)
        signed["signed_at"] = int(time.time())
        raw = self.kms.sign(  # type: ignore[attr-defined]
            self.kid, _message(signed), role="receipt", now=signed["signed_at"]
        )
        if not isinstance(raw, bytes):
            raise ProtocolError("signature operation failed")
        signed["signature"] = "ed25519:" + raw.hex()
        record_replay(signed, "issue", "gateway-receipt")
        return signed

    def verify(self, receipt: dict[str, object]) -> bool:
        signature = receipt.get("signature")
        if not isinstance(signature, str) or not signature.startswith("ed25519:"):
            return False
        signed_at = receipt.get("signed_at")
        if type(signed_at) is not int:
            return False
        raw = bytes.fromhex(signature.split(":", 1)[1])
        self.kms.verify(  # type: ignore[attr-defined]
            str(receipt.get("key_id", "")),
            _message(receipt),
            raw,
            now=signed_at,
        )
        record_replay(receipt, "verify", "gateway-receipt")
        return True
