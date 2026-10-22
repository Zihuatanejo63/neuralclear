"""Opt-in escrow-v1 evidence policy. Authentication is not execution attestation."""

from copy import deepcopy

from .core import ProtocolError
from .escrow import EscrowLedger
from .journal import mutation
from .proofs import verify_result
from .wire import ZERO_HASH, verify_signature


class StrictEscrowLedger(EscrowLedger):
    """Strict decisions require k distinct trusted Ed25519 keys (default k=1).

    The deterministic policy refunds unmetered credit and pays signed deliveries
    at the agreed rate. It cannot assess semantic quality or dishonest signers.
    """

    _state_fields = EscrowLedger._state_fields + ("_decisions", "_deliveries")

    def __init__(self, *, arbitrator_keys, provider_keys, quorum=1, **kwargs):
        if (
            type(quorum) is not int
            or not 1 <= quorum <= len(arbitrator_keys)
            or any(v[0] != "Ed25519" for v in arbitrator_keys.values())
            or len({v[1] for v in arbitrator_keys.values()}) != len(arbitrator_keys)
        ):
            raise ProtocolError("invalid Ed25519 quorum policy")
        self._arbitrators = deepcopy(arbitrator_keys)
        self._providers = deepcopy(provider_keys)
        self._quorum = quorum
        self._decisions, self._deliveries = {}, {}
        self._resolving = False
        super().__init__(**kwargs)

    @mutation
    def meter_verified(self, transaction_id, units, result, proof):
        if not isinstance(proof, dict):
            raise ProtocolError("strict profile requires signed result; mock/TEE/ZK unsupported")
        provider = self.get(transaction_id)["provider"]
        keys = self._providers.get(provider, {})
        verify_result(result, proof, transaction_id, keys)
        entry = super().meter(transaction_id, units, proof["result_hash"])
        self._deliveries[entry["hash"]] = deepcopy(proof)
        return entry

    @mutation
    def meter(self, *args, **kwargs):
        raise ProtocolError("strict profile requires meter_verified")

    @mutation
    def transition(self, transaction_id, target, **kwargs):
        record = self.get(transaction_id)
        if record["state"] == "DISPUTED" and target in {"SETTLED", "REFUNDED", "SLASHED"}:
            if not self._resolving:
                raise ProtocolError("strict resolution requires signed evidence decision")
        if target == "PROOF_VERIFIED" and not self.chain(transaction_id):
            raise ProtocolError("strict profile requires verified delivery")
        return super().transition(transaction_id, target, **kwargs)

    def decision(self, transaction_id, decision_id):
        record = self.get(transaction_id)
        if record["state"] != "DISPUTED":
            raise ProtocolError("decision requires frozen dispute")
        chain = self.chain(transaction_id)
        # Empty evidence is anchored to the complete empty chain, not an
        # omitted evidence field. Entries cannot be added while frozen.
        return dict(
            decision_id=decision_id,
            transaction_id=transaction_id,
            revision=record["revision"],
            currency=self.currency,
            chain_head=chain[-1]["hash"] if chain else ZERO_HASH,
            chain_length=len(chain),
            evidence=[dict(seq=e["seq"], hash=e["hash"]) for e in chain],
            amount=sum(e["amount"] for e in chain),
            fee=0,
            policy="signed-metered-v1",
        )

    @mutation
    def resolve(self, decision, signatures):
        if (
            not isinstance(decision, dict)
            or not isinstance(decision.get("decision_id"), str)
            or not isinstance(signatures, list)
        ):
            raise ProtocolError("invalid decision")
        did = decision["decision_id"]
        if not did or did in self._decisions:
            raise ProtocolError("decision replay")
        tx = decision.get("transaction_id")
        if decision != self.decision(tx, did):
            raise ProtocolError("decision evidence or allocation mismatch")
        approved = set()
        for signature in signatures:
            if not isinstance(signature, dict):
                raise ProtocolError("invalid decision signature")
            if {
                k: v for k, v in signature.items() if k not in {"algorithm", "key_id", "signature"}
            } != decision:
                raise ProtocolError("signature decision mismatch")
            verify_signature(signature, self._arbitrators, domain="decision")
            approved.add(signature["key_id"])
        if len(approved) < self._quorum:
            raise ProtocolError("decision quorum not met")
        self._resolving = True
        try:
            result = self.transition(
                tx, "SETTLED" if decision["amount"] else "REFUNDED", amount=decision["amount"]
            )
            self._decisions[did] = deepcopy(dict(decision=decision, signatures=signatures))
            return result
        finally:
            self._resolving = False

    def decision_record(self, decision_id):
        with self._lock:
            if decision_id not in self._decisions:
                raise ProtocolError("unknown decision")
            return deepcopy(self._decisions[decision_id])
