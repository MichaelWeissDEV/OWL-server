"""Password hashing, API token generation and constant-time comparison."""

from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()  # Argon2id with the library's current recommended parameters
MIN_PASSWORD_LENGTH = 12
TOKEN_PREFIX = "owl_"


class WeakPassword(ValueError):
    pass


def check_password_policy(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPassword(f"The password must have at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > 1024:
        raise WeakPassword("The password is too long")
    if password.lower() == password and password.isalpha():
        raise WeakPassword("The password is too simple: mix in digits or other characters")


def hash_password(password: str) -> str:
    check_password_policy(password)
    return _hasher.hash(password)


def verify_password(password: str, hashed: str | None) -> bool:
    """Verify in (nearly) constant time; a missing hash still costs one hash computation."""
    if not hashed:
        _hasher.hash("dummy-password-to-equalise-timing")
        return False
    try:
        return _hasher.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    return _hasher.check_needs_rehash(hashed)


def new_token() -> tuple[str, str, str]:
    """``(secret, display prefix, sha256 of the secret)``. Only the hash is stored."""
    secret = TOKEN_PREFIX + secrets.token_urlsafe(32)
    return secret, secret[:12], hash_token(secret)


def hash_token(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def same(a: str, b: str) -> bool:
    return secrets.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
