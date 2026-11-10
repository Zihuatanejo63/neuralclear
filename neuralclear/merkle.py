"""Domain-separated Merkle inclusion proofs for authenticated metering chains.

The root must be trusted independently (or checked against a verified receipt
and its full chain). A self-supplied root is not evidence of execution.
"""

import hashlib

from .core import ProtocolError
from .wire import canonical, digest


def leaf(entry):
    if not isinstance(entry, dict) or entry.get("hash") != digest(
        {k: v for k, v in entry.items() if k != "hash"}
    ):
        raise ProtocolError("invalid meter entry")
    return hashlib.sha256(b"\x00" + canonical(entry)).digest()


def parent(left, right):
    return hashlib.sha256(b"\x01" + left + right).digest()


def inclusion(chain, index):
    if type(index) is not int or not 0 <= index < len(chain):
        raise ProtocolError("invalid inclusion index")
    nodes = [leaf(e) for e in chain]
    siblings, cursor = [], index
    while len(nodes) > 1:
        siblings.append(nodes[cursor ^ 1 if cursor ^ 1 < len(nodes) else cursor].hex())
        nodes = [
            parent(nodes[i], nodes[min(i + 1, len(nodes) - 1)]) for i in range(0, len(nodes), 2)
        ]
        cursor //= 2
    return dict(index=index, count=len(chain), siblings=siblings, root=nodes[0].hex())


def verify_inclusion(entry, proof, trusted_root, trusted_count):
    try:
        if set(proof) != {"index", "count", "siblings", "root"}:
            raise ProtocolError("invalid inclusion fields")
        index, count = proof["index"], proof["count"]
        if (
            type(index) is not int
            or type(count) is not int
            or count != trusted_count
            or not 0 <= index < count
            or entry["seq"] != index
            or proof["root"] != trusted_root
        ):
            raise ProtocolError("inclusion context mismatch")
        node = leaf(entry)
        siblings = iter(proof["siblings"])
        while count > 1:
            encoded = next(siblings)
            sibling = bytes.fromhex(encoded)
            if len(sibling) != 32 or sibling.hex() != encoded:
                raise ProtocolError("invalid sibling")
            if index == count - 1 and count % 2 and sibling != node:
                raise ProtocolError("invalid duplicated leaf")
            node = parent(sibling, node) if index % 2 else parent(node, sibling)
            index, count = index // 2, (count + 1) // 2
        if next(siblings, None) is not None or node.hex() != trusted_root:
            raise ProtocolError("inclusion root mismatch")
        return True
    except (KeyError, TypeError, ValueError, StopIteration) as exc:
        raise ProtocolError("malformed inclusion proof") from exc
