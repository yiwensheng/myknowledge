#!/usr/bin/env python3
"""服务器上测试虎皮椒网关连通与下单（运维诊断用）。"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import xunhupay_config, xunhupay_ssl_verify  # noqa: E402
from app import xunhupay  # noqa: E402
from app.xunhupay import _ssl_context  # noqa: E402


def test_https(gateway: str) -> None:
    print(f"=== HTTPS POST {gateway} ===")
    req = urllib.request.Request(gateway, data=b"version=1.1", method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=20, context=_ssl_context()) as resp:
            body = resp.read(500).decode(errors="replace")
            print(f"status={resp.status}")
            print(f"body[:500]={body}")
    except urllib.error.HTTPError as exc:
        print(f"HTTPError {exc.code}: {exc.read()[:500].decode(errors='replace')}")
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc!r}")


def test_create_payment() -> None:
    cfg = xunhupay_config()
    print("=== config ===")
    print(
        json.dumps(
            {
                "appid": cfg["appid"][:4] + "****" if cfg["appid"] else "",
                "gateway": cfg["gateway"],
                "notify_url": cfg["notify_url"],
                "has_secret": bool(cfg["appsecret"]),
                "ssl_verify": xunhupay_ssl_verify(),
            },
            ensure_ascii=False,
        )
    )
    print("=== create_payment (test order) ===")
    try:
        result = xunhupay.create_payment("test000000000001", 19.0, "易知订阅-month")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc
    print("OK")


def main() -> int:
    cfg = xunhupay_config()
    test_https(cfg["gateway"] or "https://api.xunhupay.com/payment/do.html")
    if len(sys.argv) > 1 and sys.argv[1] == "--ping-only":
        return 0
    test_create_payment()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
