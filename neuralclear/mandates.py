"""Signed escrow-v1 mandates. Trust keys and owner binding are out-of-band."""

from .core import ProtocolError
from .wire import sign, verify_signature, PROFILE, MAX_INTEGER

FIELDS = set(
    "profile mandate_id owner agent currency allowed_capabilities max_per_task "
    "max_daily max_total valid_until requires_human_approval_above algorithm key_id signature".split()
)


def issue_mandate(body, key, key_id, algorithm="HMAC-SHA256"):
    return sign(dict(body, profile=PROFILE), key, key_id, algorithm, domain="mandate")


def validate_mandate(mandate, trusted_keys):
    """trusted_keys[key_id] = (owner, algorithm, public-or-shared-key)."""
    try:
        if set(mandate) != FIELDS or mandate["profile"] != PROFILE:
            raise ProtocolError("invalid mandate fields")
        owner, algorithm, key = trusted_keys[mandate["key_id"]]
        if owner != mandate["owner"]:
            raise ProtocolError("mandate owner/key mismatch")
        verify_signature(mandate, {mandate["key_id"]: (algorithm, key)}, domain="mandate")
        for name in ("mandate_id", "owner", "agent", "currency"):
            if not isinstance(mandate[name], str) or not mandate[name]:
                raise ProtocolError("invalid mandate identifier")
        caps = mandate["allowed_capabilities"]
        if (
            not isinstance(caps, list)
            or not caps
            or any(not isinstance(c, str) or not c for c in caps)
        ):
            raise ProtocolError("invalid mandate capabilities")
        for name in (
            "max_per_task",
            "max_daily",
            "max_total",
            "valid_until",
            "requires_human_approval_above",
        ):
            if type(mandate[name]) is not int or not 0 <= mandate[name] <= MAX_INTEGER:
                raise ProtocolError("invalid mandate limit")
        return True
    except (KeyError, TypeError, ValueError) as exc:
        raise ProtocolError("invalid mandate") from exc
