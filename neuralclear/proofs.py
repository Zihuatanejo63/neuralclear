"""Signed result proofs: the trust upgrade from MockProof.

Provider signs a digest of (transaction context + output hash); the buyer —
or any third party holding the provider's verification key — checks it
before settlement. Stdlib HMAC today; the interface is shaped so an ed25519
implementation (`cryptography` / `pynacl`) drops in without touching call
sites: same `sign_result` / `verify` surface, different `scheme` string.

    keys = ProofKeyring()
    keys.register("agent.worker", secret="provider_secret")

    proof = SignedResultProof.sign(
        signer=keys.signer_for("agent.worker"),
        capability="summarize.pdf",
        output={"summary": "..."},
    )
    proof.verify_with(keys.verifier_for("agent.worker"))  # True
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from .core import ProofLevel, ProtocolError
from .wire import canonical, verify_signature


def output_digest(output: object) -> str:
    body = json.dumps(output, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


class HMACKey:
    """Symmetric signing key. Production swap: Ed25519PrivateKey/PublicKey."""

    scheme = "hmac-sha256"

    def __init__(self, secret: str) -> None:
        self._secret = secret.encode("utf-8")

    def sign(self, message: str) -> str:
        return hmac.new(self._secret, message.encode("utf-8"), hashlib.sha256).hexdigest()

    def verify(self, message: str, signature: str) -> bool:
        return hmac.compare_digest(self.sign(message), signature)


class ProofKeyring:
    """Maps agent_id -> key. A hosted deployment backs this with a KMS;
    the sandbox keeps it in memory."""

    def __init__(self) -> None:
        self._keys: dict[str, HMACKey] = {}

    def register(self, agent_id: str, secret: str) -> None:
        self._keys[agent_id] = HMACKey(secret)

    def signer_for(self, agent_id: str) -> HMACKey:
        key = self._keys.get(agent_id)
        if key is None:
            raise ProtocolError(f"no signing key for {agent_id}")
        return key

    verifier_for = signer_for  # symmetric scheme; asymmetric splits these


@dataclass
class SignedResultProof:
    """SIGNED_RESULT level proof carrying a verifiable signature."""

    agent_id: str = ""
    capability: str = ""
    digest: str = ""
    signed_at: str = ""
    signature: str = ""
    nonce: str = ""
    signed_at_unix: int = 0
    scheme: str = HMACKey.scheme
    proof_level: ProofLevel = field(default=ProofLevel.SIGNED_RESULT)
    _verifier: HMACKey | None = field(default=None, repr=False, compare=False)

    # -- construction ------------------------------------------------------
    @classmethod
    def sign(
        cls, signer: HMACKey, agent_id: str, capability: str, output: object
    ) -> "SignedResultProof":
        import secrets
        import time

        from .replay import record_replay, replay_store_path

        digest = output_digest(output)
        signed_at = datetime.now(timezone.utc).isoformat()
        nonce = ""
        signed_at_unix = 0
        if replay_store_path() or os.environ.get("NEURALCLEAR_MODE") == "production":
            nonce = secrets.token_hex(16)
            signed_at_unix = int(time.time())
        message = cls._message(agent_id, capability, digest, signed_at, nonce, signed_at_unix)
        proof = cls(
            agent_id=agent_id,
            capability=capability,
            digest=digest,
            signed_at=signed_at,
            signature=signer.sign(message),
            nonce=nonce,
            signed_at_unix=signed_at_unix,
        )
        if nonce:
            record_replay(
                {"nonce": nonce, "signed_at": signed_at_unix}, "issue", "hmac-result-proof"
            )
        return proof

    @staticmethod
    def _message(
        agent_id: str,
        capability: str,
        digest: str,
        signed_at: str,
        nonce: str = "",
        signed_at_unix: int = 0,
    ) -> str:
        parts = [agent_id, capability, digest, signed_at]
        if nonce:
            parts.extend([nonce, str(signed_at_unix)])
        return "|".join(parts)

    # -- verification ------------------------------------------------------
    def bind_verifier(self, verifier: HMACKey) -> "SignedResultProof":
        """Attach the verification key so `verify()` (the TaskProof interface
        used by ClearingService) checks the real signature."""
        self._verifier = verifier
        return self

    def verify_with(self, verifier: HMACKey) -> bool:
        nonce = getattr(self, "nonce", "")
        unix = getattr(self, "signed_at_unix", 0)
        message = self._message(
            self.agent_id, self.capability, self.digest, self.signed_at, nonce, unix
        )
        valid = verifier.verify(message, self.signature)
        if valid and nonce:
            from .replay import record_replay

            record_replay({"nonce": nonce, "signed_at": unix}, "verify", "hmac-result-proof")
        return valid

    def verify(self) -> bool:
        if self._verifier is None:
            return False  # unverifiable proof must not settle
        return self.verify_with(self._verifier)

    def matches_output(self, output: object) -> bool:
        return self.digest == output_digest(output)

    def to_json(self) -> dict[str, object]:
        return {
            "proof_level": self.proof_level.value,
            "scheme": self.scheme,
            "agent_id": self.agent_id,
            "capability": self.capability,
            "digest": self.digest,
            "signed_at": self.signed_at,
            "signed_at_unix": self.signed_at_unix,
            "nonce": self.nonce,
            "signature": self.signature,
        }


# ---------------------------------------------------------------------------
# Escrow-v1 result authentication (opt-in profile)
#
# Separate from SignedResultProof above. This checks the escrow-v1 wire
# envelope. TEEVerifier and ZKVerifier are interfaces only; no attestation
# or zero-knowledge implementation is shipped.
# ---------------------------------------------------------------------------


def verify_result(result, proof, transaction_id, keys, *, signer=None):
    required = {"transaction_id", "result_hash", "algorithm", "key_id", "signature"}
    allowed = required | {"nonce", "signed_at"}
    if (
        not required <= set(proof) <= allowed
        or proof["transaction_id"] != transaction_id
        or proof["result_hash"] != hashlib.sha256(canonical(result)).hexdigest()
    ):
        raise ProtocolError("result proof mismatch")
    return verify_signature(proof, keys, domain="result", signer=signer)


class TEEVerifier(Protocol):
    """Interface only. No attestation implementation is shipped."""

    def verify(self, attestation: dict, expected_result_hash: str) -> bool: ...


class ZKVerifier(Protocol):
    """Interface only. No proof system or verification key is shipped."""

    def verify(self, proof: dict, expected_result_hash: str) -> bool: ...
