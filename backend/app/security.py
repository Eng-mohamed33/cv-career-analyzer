import base64
import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

import bcrypt
import jwt

JWT_ALGORITHM = "HS256"
TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", str(7 * 24 * 3600)))


def _load_secret() -> str:
    """JWT_SECRET from the environment, else a random secret persisted next to the DB.

    Persisting it means dev sessions survive server restarts without ever
    committing a secret (`.jwt_secret` is git-ignored).
    """
    from_env = os.getenv("JWT_SECRET")
    if from_env:
        return from_env
    path = Path(__file__).resolve().parent.parent / ".jwt_secret"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    generated = secrets.token_urlsafe(48)
    path.write_text(generated, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass  # e.g. Windows
    return generated


JWT_SECRET = _load_secret()


def _prehash(password: str) -> bytes:
    # bcrypt only reads the first 72 bytes; pre-hashing removes that limit
    # (and any NUL-byte problems) without weakening the password.
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, stored: str) -> tuple[bool, bool]:
    """Return (is_valid, needs_rehash). Old unsalted SHA-256 hashes still verify once."""
    if stored.startswith("$2"):
        try:
            return bcrypt.checkpw(_prehash(password), stored.encode("ascii")), False
        except ValueError:
            return False, False
    legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy, stored), True


def create_token(username: str) -> str:
    now = int(time.time())
    return jwt.encode({"sub": username, "iat": now, "exp": now + TOKEN_TTL_SECONDS}, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> str:
    """Return the username or raise jwt.PyJWTError."""
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"require": ["exp", "sub"]})
    return str(payload["sub"])


# Verified against when the username does not exist, so "unknown user" and
# "wrong password" take the same time and cannot be told apart by timing.
DUMMY_HASH = hash_password("timing-equalizer-not-a-real-password")
