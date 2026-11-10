"""Constant-time comparison for API keys and other shared secrets."""

from __future__ import annotations

import hashlib
import hmac


def const_equal(provided: object, expected: object) -> bool:
    """Compare two secrets without taking the `==` branch on the raw values.

    Both sides are hashed to a fixed length first so differing lengths still go
    through hmac.compare_digest. An empty expected secret never matches.
    """
    if not isinstance(expected, str) or expected == "":
        return False
    provided_bytes = provided.encode("utf-8") if isinstance(provided, str) else b""
    left = hashlib.sha256(provided_bytes).digest()
    right = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(left, right)
