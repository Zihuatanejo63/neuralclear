"""Offline escrow-v1 receipt verifier. Does not instantiate or import Ledger."""

from __future__ import annotations

import argparse
from pathlib import Path
import re

from .core import ProtocolError
from .wire import PROFILE, ZERO_HASH, MAX_INTEGER, canonical, digest, load_json
from .wire import verify_signature
from .merkle import inclusion, verify_inclusion


def verify_meter_inclusion(receipt, chain, keys, entry, proof):
    """Authenticate root through the signed receipt's full chain, not user input."""
    verify(receipt, chain, keys)
    trusted = inclusion(chain, 0)
    return verify_inclusion(entry, proof, trusted["root"], len(chain))


# Deliberately independent of the engine's state table: this verifies the wire spec.
EDGES = {
    "QUOTE_REQUESTED": {"QUOTE_ACCEPTED", "EXPIRED"},
    "QUOTE_ACCEPTED": {"TASK_SUBMITTED", "EXPIRED"},
    "TASK_SUBMITTED": {"TASK_RUNNING", "DISPUTED"},
    "TASK_RUNNING": {"RESULT_DELIVERED", "DISPUTED"},
    "RESULT_DELIVERED": {"PROOF_VERIFIED", "DISPUTED"},
    "PROOF_VERIFIED": {"SETTLED", "DISPUTED"},
    "SETTLED": {"DISPUTED"},
    "DISPUTED": {"SETTLED", "REFUNDED", "SLASHED"},
    "REFUNDED": set(),
    "SLASHED": set(),
    "EXPIRED": set(),
}
RECEIPT_FIELDS = set(
    "profile transaction_id buyer provider currency budget fee_limit funded "
    "amount fee refund state revision history unit rate result_hash "
    "chain_head chain_length deltas algorithm key_id signature".split()
)
METER_FIELDS = set(
    "transaction_id currency seq previous units unit rate amount result_hash hash".split()
)


def require(condition, message):
    if not condition:
        raise ProtocolError(message)


def natural(value):
    require(type(value) is int and 0 <= value <= MAX_INTEGER, "invalid integer")


def hash_value(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value), "invalid hash")


def verify(receipt: dict, chain: list, keys: dict[str, bytes]) -> bool:
    """Return True or raise ProtocolError. Keys come from trusted out-of-band config.

    Verifies an authenticated arithmetic statement, not service quality, actual
    resource consumption, solvency, real bank payment or latest global ledger head.
    """
    try:
        return _verify(receipt, chain, keys)
    except ProtocolError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ProtocolError("malformed verification input") from exc


def _verify(receipt, chain, keys):
    require(isinstance(receipt, dict) and set(receipt) == RECEIPT_FIELDS, "receipt fields mismatch")
    canonical(receipt)
    require(receipt["profile"] == PROFILE, "unsupported profile")
    verify_signature(receipt, keys)
    for name in ("transaction_id", "buyer", "provider", "currency", "unit", "key_id"):
        value = receipt[name]
        require(
            isinstance(value, str) and value and all(33 <= ord(c) <= 126 for c in value),
            "invalid identifier",
        )
    require(receipt["buyer"] != receipt["provider"], "parties must differ")
    for name in (
        "budget",
        "fee_limit",
        "funded",
        "amount",
        "fee",
        "refund",
        "revision",
        "rate",
        "chain_length",
    ):
        natural(receipt[name])
    history = receipt["history"]
    require(
        isinstance(history, list) and history and history[0] == "QUOTE_REQUESTED", "invalid history"
    )
    for left, right in zip(history, history[1:]):
        require(left in EDGES and right in EDGES[left], "invalid state transition")
    require(
        receipt["revision"] == len(history) - 1 and receipt["state"] == history[-1],
        "history mismatch",
    )
    require(receipt["state"] in {"SETTLED", "REFUNDED", "SLASHED", "EXPIRED"}, "unresolved receipt")
    funded = receipt["budget"] + receipt["fee_limit"] if "QUOTE_ACCEPTED" in history else 0
    require(receipt["funded"] == funded, "funding mismatch")
    require(
        isinstance(chain, list) and len(chain) == receipt["chain_length"], "chain length mismatch"
    )
    previous, metered = ZERO_HASH, 0
    for index, event in enumerate(chain):
        require(isinstance(event, dict) and set(event) == METER_FIELDS, "meter fields mismatch")
        for name in ("seq", "units", "rate", "amount"):
            natural(event[name])
        require(event["seq"] == index and event["previous"] == previous, "broken chain")
        for name in ("transaction_id", "currency", "unit", "rate"):
            require(event[name] == receipt[name], "meter context mismatch")
        hash_value(event["result_hash"])
        hash_value(event["hash"])
        require(event["amount"] == event["units"] * event["rate"], "meter cost mismatch")
        require(
            event["hash"] == digest({k: v for k, v in event.items() if k != "hash"}),
            "meter hash mismatch",
        )
        previous = event["hash"]
        metered += event["amount"]
    natural(metered)
    require(not chain or "TASK_RUNNING" in history, "meter without running task")
    require(previous == receipt["chain_head"], "chain head mismatch")
    hash_value(receipt["result_hash"])
    require(
        receipt["result_hash"] == (chain[-1]["result_hash"] if chain else ZERO_HASH),
        "result hash mismatch",
    )
    require(receipt["amount"] <= metered <= receipt["budget"], "award exceeds metered budget")
    require(receipt["fee"] <= receipt["fee_limit"], "fee exceeds cap")
    require(
        receipt["amount"] + receipt["fee"] + receipt["refund"] == funded,
        "escrow conservation failed",
    )
    if receipt["state"] in {"REFUNDED", "EXPIRED"}:
        require(receipt["amount"] == receipt["fee"] == 0, "refund/expiry allocation invalid")
    expected = {
        "buyer": -(receipt["amount"] + receipt["fee"]),
        "provider": receipt["amount"],
        "fee_pool": receipt["fee"],
        "escrow": 0,
    }
    deltas = receipt["deltas"]
    require(
        isinstance(deltas, dict) and all(type(v) is int for v in deltas.values()), "invalid deltas"
    )
    require(deltas == expected and sum(deltas.values()) == 0, "zero-sum clearing failed")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt")
    parser.add_argument("chain")
    parser.add_argument("--inclusion-entry", help="optional JSON meter entry")
    parser.add_argument("--inclusion-proof", help="optional JSON Merkle proof")
    parser.add_argument(
        "--key-file", required=True, help="raw shared-secret bytes; never from receipt"
    )
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--algorithm", choices=["HMAC-SHA256", "Ed25519"], default="HMAC-SHA256")
    args = parser.parse_args(argv)
    try:
        receipt = load_json(Path(args.receipt).read_text(encoding="utf-8"))
        chain = load_json(Path(args.chain).read_text(encoding="utf-8"))
        keys = {args.key_id: (args.algorithm, Path(args.key_file).read_bytes())}
        if bool(args.inclusion_entry) != bool(args.inclusion_proof):
            raise ProtocolError("both inclusion entry and proof are required")
        if args.inclusion_entry:
            verify_meter_inclusion(
                receipt,
                chain,
                keys,
                load_json(Path(args.inclusion_entry).read_text(encoding="utf-8")),
                load_json(Path(args.inclusion_proof).read_text(encoding="utf-8")),
            )
        else:
            verify(receipt, chain, keys)
    except (OSError, ProtocolError) as exc:
        print("INVALID: " + str(exc))
        return 1
    print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
