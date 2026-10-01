"""Password hashing and signed access tokens (standard library only)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
    return hmac.compare_digest(digest.hex(), digest_hex)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: str, secret: str) -> str:
    return _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())


def create_token(user_id: int, role: str, secret: str, ttl_s: int) -> str:
    payload = _b64(json.dumps({"sub": user_id, "role": role, "exp": int(time.time()) + ttl_s}).encode())
    return f"{payload}.{_sign(payload, secret)}"


def decode_token(token: str, secret: str) -> dict | None:
    try:
        payload, signature = token.split(".")
    except ValueError:
        return None
    if not hmac.compare_digest(signature, _sign(payload, secret)):
        return None
    try:
        data = json.loads(_unb64(payload))
    except ValueError:
        return None
    if data.get("exp", 0) < time.time():
        return None
    return data
