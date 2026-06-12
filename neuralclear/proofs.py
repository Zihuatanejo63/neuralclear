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
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .core import ProofLevel, ProtocolError


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
    scheme: str = HMACKey.scheme
    proof_level: ProofLevel = field(default=ProofLevel.SIGNED_RESULT)
    _verifier: HMACKey | None = field(default=None, repr=False, compare=False)

    # -- construction ------------------------------------------------------
    @classmethod
    def sign(
        cls, signer: HMACKey, agent_id: str, capability: str, output: object
    ) -> "SignedResultProof":
        digest = output_digest(output)
        signed_at = datetime.now(timezone.utc).isoformat()
        message = cls._message(agent_id, capability, digest, signed_at)
        return cls(
            agent_id=agent_id,
            capability=capability,
            digest=digest,
            signed_at=signed_at,
            signature=signer.sign(message),
        )

    @staticmethod
    def _message(agent_id: str, capability: str, digest: str, signed_at: str) -> str:
        return "|".join([agent_id, capability, digest, signed_at])

    # -- verification ------------------------------------------------------
    def bind_verifier(self, verifier: HMACKey) -> "SignedResultProof":
        """Attach the verification key so `verify()` (the TaskProof interface
        used by ClearingService) checks the real signature."""
        self._verifier = verifier
        return self

    def verify_with(self, verifier: HMACKey) -> bool:
        message = self._message(self.agent_id, self.capability, self.digest, self.signed_at)
        return verifier.verify(message, self.signature)

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
            "signature": self.signature,
        }
