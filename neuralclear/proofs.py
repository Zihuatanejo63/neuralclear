"""Escrow result authentication; no claim of TEE/ZK execution attestation."""

import hashlib
from typing import Protocol

from .core import ProtocolError
from .wire import canonical, verify_signature


def verify_result(result, proof, transaction_id, keys):
    if (
        set(proof) != {"transaction_id", "result_hash", "algorithm", "key_id", "signature"}
        or proof["transaction_id"] != transaction_id
        or proof["result_hash"] != hashlib.sha256(canonical(result)).hexdigest()
    ):
        raise ProtocolError("result proof mismatch")
    return verify_signature(proof, keys, domain="result")


class TEEVerifier(Protocol):
    """Interface only. No attestation implementation is shipped."""

    def verify(self, attestation: dict, expected_result_hash: str) -> bool: ...


class ZKVerifier(Protocol):
    """Interface only. No proof system or verification key is shipped."""

    def verify(self, proof: dict, expected_result_hash: str) -> bool: ...
