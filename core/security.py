"""
core.security
===============
Password hashing helpers.

The original PHP system stored passwords as bare MD5 hashes
(`md5($password)`), which is what you'll find in an existing XAMPP
`payroll_db.users.password` column. To guarantee "your existing data
just works" when you point this app at that database, `verify_password`
transparently recognises and checks legacy MD5 hashes.

Everything *newly* created by the Python app uses bcrypt instead
(via the `bcrypt` package) — a proper, salted, slow hash — which is
strictly more secure. There's nothing to configure: a password is
hashed with bcrypt on creation, and the verifier auto-detects which
scheme a stored hash uses.
"""
from __future__ import annotations

import hashlib
import re

import bcrypt

_MD5_RE = re.compile(r"^[a-f0-9]{32}$", re.IGNORECASE)


def hash_password(plain: str) -> str:
    """Hash a new password with bcrypt (preferred, secure scheme)."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def hash_password_legacy_md5(plain: str) -> str:
    """Produce a legacy MD5 hash — used only when we deliberately want
    parity with the original PHP scheme (e.g. writing a passcode-reset
    default password into an existing MySQL DB that other legacy
    tooling might still expect). Prefer hash_password() everywhere else.
    """
    return hashlib.md5(plain.encode("utf-8")).hexdigest()


def verify_password(plain: str, stored_hash: str) -> bool:
    """Verify a password against a stored hash, auto-detecting scheme."""
    if not stored_hash:
        return False
    if _MD5_RE.match(stored_hash):
        return hashlib.md5(plain.encode("utf-8")).hexdigest() == stored_hash.lower()
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), stored_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def is_legacy_hash(stored_hash: str) -> bool:
    return bool(stored_hash and _MD5_RE.match(stored_hash))
