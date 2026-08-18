"""渠道尾标（易知侧独立副本，协议与周易一致）。"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import struct
import time
from pathlib import Path
from typing import Any

MAGIC = b"CHNL1"
CODE_RE = re.compile(r"^P_[A-Z0-9_]{2,32}$")


def default_secret() -> str:
    return (
        os.getenv("YIZHI_CHANNEL_HMAC_SECRET")
        or os.getenv("ZHOUYI_CHANNEL_HMAC_SECRET")
        or os.getenv("CHANNEL_HMAC_SECRET")
        or "zhouyi-channel-dev-secret-change-me"
    ).strip()


def normalize_code(code: str) -> str:
    return (code or "").strip().upper()


def validate_code(code: str) -> str:
    c = normalize_code(code)
    if not CODE_RE.match(c):
        raise ValueError("渠道码须匹配 P_ 开头的大写字母数字下划线（2～32）")
    return c


def sign_payload(code: str, product: str, ts: int, secret: str | None = None) -> str:
    sec = (secret or default_secret()).encode("utf-8")
    msg = f"{normalize_code(code)}|{product}|{ts}".encode("utf-8")
    return hmac.new(sec, msg, hashlib.sha256).hexdigest()


def build_trailer(code: str, *, product: str = "yizhi", secret: str | None = None) -> bytes:
    c = validate_code(code)
    ts = int(time.time())
    body = {
        "c": c,
        "p": product,
        "t": ts,
        "s": sign_payload(c, product, ts, secret),
    }
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return raw + struct.pack("<I", len(raw)) + MAGIC


def parse_trailer(blob: bytes, *, secret: str | None = None, require_sig: bool = True) -> dict[str, Any] | None:
    if len(blob) < 9 + 2:
        return None
    if blob[-5:] != MAGIC:
        return None
    (n,) = struct.unpack("<I", blob[-9:-5])
    if n <= 0 or n > 4096 or len(blob) < 9 + n:
        return None
    raw = blob[-(9 + n) : -9]
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    code = normalize_code(str(data.get("c") or ""))
    product = str(data.get("p") or "").strip() or "yizhi"
    try:
        ts = int(data.get("t") or 0)
    except Exception:
        return None
    sig = str(data.get("s") or "").strip().lower()
    if not CODE_RE.match(code):
        return None
    if require_sig:
        expect = sign_payload(code, product, ts, secret)
        if not sig or not hmac.compare_digest(sig, expect):
            return None
    return {"code": code, "product": product, "t": ts, "s": sig, "raw": data}


def read_channel_from_file(path: Path, *, secret: str | None = None, require_sig: bool = True) -> dict[str, Any] | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return parse_trailer(data[-8192:], secret=secret, require_sig=require_sig)


def stamp_file(
    src: Path,
    dest: Path,
    code: str,
    *,
    product: str = "yizhi",
    secret: str | None = None,
) -> dict[str, Any]:
    raw = src.read_bytes()
    while True:
        if raw[-5:] != MAGIC:
            break
        (n,) = struct.unpack("<I", raw[-9:-5])
        if n <= 0 or n > 4096 or len(raw) < 9 + n:
            break
        raw = raw[: -(9 + n)]
    trailer = build_trailer(code, product=product, secret=secret)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw + trailer)
    info = parse_trailer(trailer, secret=secret, require_sig=True)
    assert info is not None
    return info
