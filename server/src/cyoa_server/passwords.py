"""Password hashing with scrypt (from the standard library)."""

from __future__ import annotations

import hashlib
import hmac
import secrets

N, R, P = 2**14, 8, 1
KEY_LENGTH = 32


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=KEY_LENGTH)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = _derive(password, salt, N, R, P)
    return f"scrypt${N}${R}${P}${salt.hex()}${key.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, key = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = bytes.fromhex(key)
        derived = _derive(password, bytes.fromhex(salt), int(n), int(r), int(p))
    except ValueError:
        return False
    return hmac.compare_digest(derived, expected)


# Checked against when a username doesn't exist, so that takes as long as a wrong password.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
