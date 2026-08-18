"""Minimal HMAC-SHA256 JWT (no PyJWT dependency)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def sign_token(payload: dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    h = _b64url(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    msg = f"{h}.{p}".encode()
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url(sig)}"


def verify_token(token: str, secret: str) -> dict[str, Any] | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        h, p, s = parts
        msg = f"{h}.{p}".encode()
        expected = hmac.new(secret.encode(), msg, hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url(expected), s):
            return None
        payload = json.loads(_b64url_decode(p))
        exp = payload.get("exp")
        if exp is not None and int(exp) < int(time.time()):
            return None
        return payload
    except (ValueError, json.JSONDecodeError, TypeError):
        return None


def make_license_token(
    *,
    license_id: str,
    device_id: str,
    plan: str,
    expires_at: int,
    secret: str,
) -> str:
    now = int(time.time())
    payload = {
        "sub": license_id,
        "device_id": device_id,
        "plan": plan,
        "iat": now,
        "exp": expires_at,
    }
    return sign_token(payload, secret)
