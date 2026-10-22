"""Pure Ed25519 (RFC 8032), reference interoperability implementation.

Python bigint operations are NOT constant-time. Do not use this reference signer
for production secrets exposed to timing/side-channel attackers. Verification
uses canonical encodings, S < L and non-identity prime-subgroup points.
"""

from hashlib import sha512

P = 2**255 - 19
L = 2**252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, P - 2, P) % P
I = pow(2, (P - 1) // 4, P)
IDENTITY = (0, 1, 1, 0)


def _decode(encoded):
    if not isinstance(encoded, bytes) or len(encoded) != 32:
        raise ValueError("invalid point length")
    value = int.from_bytes(encoded, "little")
    y, sign = value & ((1 << 255) - 1), value >> 255
    if y >= P:
        raise ValueError("non-canonical point")
    xx = (y * y - 1) * pow(D * y * y + 1, P - 2, P) % P
    x = pow(xx, (P + 3) // 8, P)
    if x * x % P != xx:
        x = x * I % P
    if x * x % P != xx or (x == 0 and sign):
        raise ValueError("invalid curve point")
    if x & 1 != sign:
        x = P - x
    return x, y, 1, x * y % P


def _add(a, b):
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    aa = (y1 - x1) * (y2 - x2) % P
    bb = (y1 + x1) * (y2 + x2) % P
    cc = 2 * D * t1 * t2 % P
    dd = 2 * z1 * z2 % P
    e, f, g, h = bb - aa, dd - cc, dd + cc, bb + aa
    return e * f % P, g * h % P, f * g % P, e * h % P


def _mul(point, scalar):
    result = IDENTITY
    while scalar:
        if scalar & 1:
            result = _add(result, point)
        point = _add(point, point)
        scalar >>= 1
    return result


def _encode(point):
    x, y, z, _ = point
    inverse = pow(z, P - 2, P)
    x, y = x * inverse % P, y * inverse % P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


BASE = _decode(bytes.fromhex("58" + "66" * 31))


def _expand(seed):
    if not isinstance(seed, bytes) or len(seed) != 32:
        raise ValueError("Ed25519 seed must be 32 bytes")
    h = sha512(seed).digest()
    scalar = int.from_bytes(h[:32], "little")
    scalar = (scalar & ((1 << 254) - 8)) | (1 << 254)
    return scalar, h[32:]


def public_key(seed):
    scalar, _ = _expand(seed)
    return _encode(_mul(BASE, scalar))


def _hash_scalar(data):
    return int.from_bytes(sha512(data).digest(), "little") % L


def sign(seed, message):
    scalar, prefix = _expand(seed)
    public = _encode(_mul(BASE, scalar))
    nonce = _hash_scalar(prefix + message)
    r = _encode(_mul(BASE, nonce))
    s = (nonce + _hash_scalar(r + public + message) * scalar) % L
    return r + s.to_bytes(32, "little")


def verify(public, message, signature):
    try:
        if not isinstance(signature, bytes) or len(signature) != 64:
            return False
        a, r = _decode(public), _decode(signature[:32])
        identity = _encode(IDENTITY)
        for point in (a, r):
            if _encode(point) == identity or _encode(_mul(point, L)) != identity:
                return False
        s = int.from_bytes(signature[32:], "little")
        if s >= L:
            return False
        k = _hash_scalar(signature[:32] + public + message)
        return _encode(_mul(BASE, s)) == _encode(_add(r, _mul(a, k)))
    except (ValueError, TypeError):
        return False
