"""Cryptographic verification for commercial SpendingMandate signatures.

Sandbox receipts may still carry the historical unsigned demo signature.
Production must verify an Ed25519 signature over the mandate body with a KMS
public key before any receipt is issued. Mandate revocation is a separate
operation and does not revoke the signing key.
"""

from __future__ import annotations

import json

from .core import ProtocolError, SpendingMandate
from .kms import LocalKms


def mandate_message(mandate: SpendingMandate) -> bytes:
    body = {
        "owner": mandate.owner,
        "agent": mandate.agent,
        "allowed_capabilities": list(mandate.allowed_capabilities),
        "max_per_task": mandate.max_per_task.to_json(),
        "max_daily": mandate.max_daily.to_json(),
        "valid_until": mandate.valid_until,
        "requires_human_approval_above": mandate.requires_human_approval_above.to_json(),
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_spending_mandate(mandate: SpendingMandate, kms: LocalKms, kid: str, *, now: int) -> str:
    signature = kms.sign(kid, mandate_message(mandate), role="mandate", now=now)
    return f"ed25519:{kid}:{signature.hex()}"


def verify_spending_mandate(mandate: SpendingMandate, kms: LocalKms, *, now: int) -> None:
    parts = mandate.signature.split(":")
    if len(parts) != 3 or parts[0] != "ed25519" or not parts[1] or not parts[2]:
        raise ProtocolError("mandate signature is not a verified Ed25519 signature")
    try:
        signature = bytes.fromhex(parts[2])
    except ValueError as exc:
        raise ProtocolError("mandate signature is not a verified Ed25519 signature") from exc
    kms.verify(parts[1], mandate_message(mandate), signature, now=now)
