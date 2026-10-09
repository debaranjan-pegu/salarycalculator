"""Authentication and password handling for the Salary Calculator.

Everything here is standard library only:

* passwords are stored as PBKDF2-HMAC-SHA256 with a random per-user salt and a
  high iteration count (never in clear text),
* session cookies carry a random 256-bit token; only its SHA-256 digest is
  stored, so a database leak does not expose usable sessions,
* comparisons are constant-time.

This is a local, single-machine app bound to 127.0.0.1, so the threat model is
"someone with the machine". The measures above make the stored credentials and
sessions useless on their own; they are not a substitute for OS-level access
control.
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import re
import secrets

ALGO = "pbkdf2_sha256"
ITERATIONS = 240_000
SESSION_DAYS = 14
MAX_FAILED_ATTEMPTS = 6
LOCK_MINUTES = 15

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,32}$")


def now() -> datetime.datetime:
    return datetime.datetime.utcnow()


def iso(dt: datetime.datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------ passwords

def hash_password(password: str, iterations: int = ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{ALGO}${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != ALGO:
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(dk.hex(), digest_hex)
    except (ValueError, AttributeError):
        return False


def password_problems(password: str) -> list[str]:
    issues = []
    if len(password or "") < 8:
        issues.append("at least 8 characters")
    if not re.search(r"[A-Za-z]", password or ""):
        issues.append("a letter")
    if not re.search(r"\d", password or ""):
        issues.append("a number")
    return issues


def email_problems(email: str) -> list[str]:
    return [] if EMAIL_RE.match(email or "") else ["a valid email address"]


def username_problems(username: str) -> list[str]:
    return [] if USERNAME_RE.match(username or "") else \
        ["3-32 characters (letters, numbers, dot, dash, underscore)"]


# ------------------------------------------------------------------ sessions

def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def expiry() -> str:
    return iso(now() + datetime.timedelta(days=SESSION_DAYS))


# ------------------------------------------------------------------ recovery

def new_recovery_code() -> str:
    """A one-time code shown once at setup, used to recover the admin account."""
    raw = secrets.token_hex(16).upper()
    return "-".join(raw[i:i + 4] for i in range(0, len(raw), 4))


def temp_password() -> str:
    return "Tmp-" + secrets.token_urlsafe(9)


def generate_password(length: int = 14) -> str:
    alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))
