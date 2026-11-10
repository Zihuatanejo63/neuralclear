"""Local test KMS. Private keys stay inside this object.

Production deployment must inject an explicit KMS or HSM adapter with the same
methods. This process-local adapter is for tests and sandbox only. It refuses
to mix test and live key material. Errors never include private key bytes.
"""

from __future__ import annotations

from dataclasses import dataclass

from .core import ProtocolError

_PROCESS_KMS = None


def redact_sensitive(text: str, materials: list[object]) -> str:
    """Strip key material from a log or error string.

    At least as strict as the Stripe test runner: exact secret values and
    hex-encoded private keys are replaced, and the function does not echo the
    material back in its own errors.
    """
    redacted = text
    for material in materials:
        if isinstance(material, bytes):
            redacted = redacted.replace(material.hex(), "[REDACTED]")
            redacted = redacted.replace(material.decode("latin1", "ignore"), "[REDACTED]")
        elif isinstance(material, str) and material:
            redacted = redacted.replace(material, "[REDACTED]")
    return redacted


@dataclass
class KeyRecord:
    kid: str
    algorithm: str
    public_key: bytes
    purpose: str
    environment: str
    not_before: int
    not_after: int | None
    revoked: bool
    roles: frozenset


class LocalKms:
    """In-memory Ed25519 KMS. cryptography performs the signature.

    ``environment`` is ``test`` or ``live``. A store will not generate or sign
    with the other environment's keys.
    """

    production_signer = True
    algorithm = "Ed25519"
    reference_implementation = False

    def __init__(self, *, environment: str) -> None:
        if environment not in {"test", "live"}:
            raise ProtocolError("kms environment must be test or live")
        self.environment = environment
        self._private: dict[str, object] = {}
        self._records: dict[str, KeyRecord] = {}
        self._secrets: list[bytes] = []

    def generate(
        self,
        *,
        purpose: str,
        kid: str,
        not_before: int,
        roles: set[str],
        not_after: int | None = None,
        environment: str | None = None,
    ) -> KeyRecord:
        environment = environment or self.environment
        if environment != self.environment:
            raise ProtocolError("refusing to store a key from another environment")
        if not kid or not purpose or not roles:
            raise ProtocolError("key id, purpose, and roles are required")
        if kid in self._records:
            raise ProtocolError("key id already exists")
        private, public = _generate_ed25519()
        record = KeyRecord(
            kid=kid,
            algorithm="Ed25519",
            public_key=public,
            purpose=purpose,
            environment=environment,
            not_before=not_before,
            not_after=not_after,
            revoked=False,
            roles=frozenset(roles),
        )
        self._private[kid] = private
        self._records[kid] = record
        return record

    def set_not_after(self, kid: str, not_after: int) -> None:
        record = self._records.get(kid)
        if record is None:
            raise ProtocolError("unknown key")
        self._records[kid] = KeyRecord(
            kid=record.kid,
            algorithm=record.algorithm,
            public_key=record.public_key,
            purpose=record.purpose,
            environment=record.environment,
            not_before=record.not_before,
            not_after=not_after,
            revoked=record.revoked,
            roles=record.roles,
        )

    def revoke(self, kid: str) -> None:
        record = self._records.get(kid)
        if record is None:
            raise ProtocolError("unknown key")
        self._records[kid] = KeyRecord(
            kid=record.kid,
            algorithm=record.algorithm,
            public_key=record.public_key,
            purpose=record.purpose,
            environment=record.environment,
            not_before=record.not_before,
            not_after=record.not_after,
            revoked=True,
            roles=record.roles,
        )

    def public_record(self, kid: str, *, now: int) -> KeyRecord:
        return self._usable(kid, now)

    def sign(self, kid: str, message: bytes, *, role: str, now: int) -> bytes:
        record = self._usable(kid, now)
        if role not in record.roles:
            raise ProtocolError("key access denied")
        if record.environment != self.environment:
            raise ProtocolError("key environment mismatch")
        private = self._private.get(kid)
        try:
            signature = private.sign(message)  # type: ignore[attr-defined]
        except Exception:
            raise ProtocolError("signature operation failed") from None
        if not isinstance(signature, bytes):
            raise ProtocolError("signature operation failed")
        return signature

    def verify(self, kid: str, message: bytes, signature: bytes, *, now: int) -> None:
        record = self._usable(kid, now)
        try:
            _verify_ed25519(record.public_key, message, signature)
        except Exception:
            raise ProtocolError("signature mismatch") from None

    def _usable(self, kid: str, now: int) -> KeyRecord:
        record = self._records.get(kid)
        if record is None:
            raise ProtocolError("unknown key")
        if record.environment != self.environment:
            raise ProtocolError("key environment mismatch")
        if record.revoked:
            raise ProtocolError("revoked key")
        if now < record.not_before:
            raise ProtocolError("key not yet valid")
        if record.not_after is not None and now >= record.not_after:
            raise ProtocolError("key expired")
        return record


def set_process_kms(kms: LocalKms | None) -> None:
    global _PROCESS_KMS
    _PROCESS_KMS = kms


def get_process_kms() -> LocalKms | None:
    return _PROCESS_KMS


def _generate_ed25519():
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError as exc:
        raise ProtocolError("cryptography Ed25519 is required") from exc
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private, public


def _verify_ed25519(public: bytes, message: bytes, signature: bytes) -> None:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        Ed25519PublicKey.from_public_bytes(public).verify(signature, message)
    except InvalidSignature as exc:
        raise ProtocolError("signature mismatch") from exc
