"""Executable signing-key rotation. This is not mandate revocation.

``revoke_mandate`` only retires a spending mandate. ``retire_key`` revokes the
signing key id. During the overlap both kids verify. After retire, the old kid
fails and the new kid still verifies.
"""

from __future__ import annotations

from .kms import LocalKms


def issue_key(kms: LocalKms, *, purpose: str, kid: str, now: int, roles: set[str]) -> str:
    record = kms.generate(purpose=purpose, kid=kid, not_before=now, roles=roles)
    return record.kid


def begin_overlap(kms: LocalKms, old_kid: str, *, now: int, overlap_seconds: int) -> None:
    """Keep the previous kid valid until ``now + overlap_seconds``."""
    kms.set_not_after(old_kid, now + overlap_seconds)


def retire_key(kms: LocalKms, kid: str) -> None:
    kms.revoke(kid)
