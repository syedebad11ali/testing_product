"""Password hashing (stdlib scrypt) and the password policy. No new dependency.

Format: ``scrypt$<n>$<r>$<p>$<salt_b64>$<hash_b64>``. Parameters travel with the hash so they can
be raised later; ``needs_rehash`` tells callers when to upgrade on a successful login.
Swap to argon2id (``argon2-cffi``) later by adding a new prefix in ``verify`` -- see docs/AUTH.md.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

N, R, P = 2**14, 8, 1
MIN_LEN, MAX_LEN = 10, 128

# Small built-in list of the most common passwords (lower-case). Extend via a file if needed.
COMMON = frozenset("""password password1 password123 passw0rd 1234567890 12345678910 qwertyuiop qwerty12345 qwerty123456
iloveyou123 letmein123 welcome123 admin12345 administrator abc1234567 1q2w3e4r5t 1qaz2wsx3edc 0123456789 9876543210
123456789012 monkey12345 dragon12345 football123 baseball123 sunshine123 princess123 pakistan123 karachi123 admin_001
karachi1234 property123 changeme123 changeme1234 trustno1234 passwordpassword 11111111111 00000000000""".split())


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=32)
    return f"scrypt${N}${R}${P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-time check. Pass ``DUMMY_HASH`` for unknown users so timing does not reveal them."""
    try:
        scheme, n, r, p, salt, digest = (stored or DUMMY_HASH).split("$")
        if scheme != "scrypt":
            return False
        calc = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(calc, base64.b64decode(digest)) and stored is not None
    except (ValueError, TypeError):
        return False


def needs_rehash(stored: str) -> bool:
    try:
        return stored.split("$")[1:4] != [str(N), str(R), str(P)]
    except IndexError:
        return True


def policy_problems(password: str, *, email: str = "", username: str = "") -> list[str]:
    """Human-readable reasons the password is not acceptable (empty list = fine)."""
    problems: list[str] = []
    if len(password) < MIN_LEN:
        problems.append(f"Use at least {MIN_LEN} characters.")
    if len(password) > MAX_LEN:
        problems.append(f"Use at most {MAX_LEN} characters.")
    low = password.lower()
    if low in COMMON or len(set(low)) <= 2:
        problems.append("That password is too common.")
    local = email.split("@")[0].lower()
    if (len(local) >= 4 and local in low) or (username and low == username.lower()):
        problems.append("Do not use your email or username in the password.")
    return problems


def is_strong_for_admin(password: str, username: str) -> bool:
    """Production gate for the seeded admin account: long, mixed and not derived from the username."""
    classes = sum(bool(x) for x in (any(c.islower() for c in password), any(c.isupper() for c in password),
                                     any(c.isdigit() for c in password), any(not c.isalnum() for c in password)))
    return len(password) >= 14 and classes >= 3 and username.lower() not in password.lower() and password.lower() not in COMMON


DUMMY_HASH = "scrypt$16384$8$1$" + _b64(b"0" * 16) + "$" + _b64(b"0" * 32)
