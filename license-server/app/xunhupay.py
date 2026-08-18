"""XunhuPay (虎皮椒) payment integration."""

from __future__ import annotations

import hashlib
import hmac
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .config import dev_mock_pay, xunhupay_config, xunhupay_ssl_verify


def _ssl_context() -> ssl.SSLContext:
    if not xunhupay_ssl_verify():
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _sign(params: dict[str, str], secret: str) -> str:
    items = sorted((k, v) for k, v in params.items() if k != "hash" and v)
    raw = "&".join(f"{k}={v}" for k, v in items) + secret
    return hashlib.md5(raw.encode()).hexdigest()


def create_payment(order_id: str, amount: float, title: str) -> dict[str, str]:
    cfg = xunhupay_config()
    if dev_mock_pay():
        mock_url = f"mock://pay/{order_id}?amount={amount}"
        return {"qr_url": mock_url, "trade_no": f"mock-{order_id}"}

    if not cfg["appid"] or not cfg["appsecret"]:
        raise RuntimeError("xunhupay not configured")

    fee = amount
    total_fee = str(int(fee)) if fee == int(fee) else f"{fee:.2f}"

    params = {
        "version": "1.1",
        "appid": cfg["appid"],
        "trade_order_id": order_id,
        "total_fee": total_fee,
        "title": title[:40],
        "time": str(int(time.time())),
        "notify_url": cfg["notify_url"],
        "return_url": cfg["return_url"] or cfg["notify_url"],
        "nonce_str": order_id[:16],
        "plugins": "yizhi",
    }
    params["hash"] = _sign(params, cfg["appsecret"])

    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(cfg["gateway"], data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=20, context=_ssl_context()) as resp:
            raw = resp.read().decode()
            data = json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"xunhupay HTTP {exc.code}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        reason = exc.reason or exc
        raise RuntimeError(f"xunhupay network error: {reason}") from exc
    except (json.JSONDecodeError, TimeoutError) as exc:
        raise RuntimeError(f"xunhupay request failed: {exc}") from exc

    if data.get("errcode") != 0:
        raise RuntimeError(data.get("errmsg") or f"xunhupay error {data.get('errcode')}")

    # PC 扫码优先 url_qrcode（可直接展示）；url 为手机端跳转链接
    qr_url = str(data.get("url_qrcode") or data.get("url") or "")
    if not qr_url:
        raise RuntimeError("xunhupay returned empty url_qrcode/url")
    return {"qr_url": qr_url, "trade_no": str(data.get("openid") or order_id)}


def verify_notify(form: dict[str, str]) -> bool:
    cfg = xunhupay_config()
    if dev_mock_pay():
        return True
    secret = cfg["appsecret"]
    if not secret:
        return False
    received = form.get("hash", "")
    expected = _sign(form, secret)
    return hmac.compare_digest(received.lower(), expected.lower())


def parse_notify(form: dict[str, str]) -> dict[str, Any]:
    status = form.get("status") or form.get("trade_status") or ""
    order_id = form.get("trade_order_id") or form.get("out_trade_no") or ""
    trade_no = form.get("transaction_id") or form.get("open_order_id") or ""
    paid = status in ("OD", "paid", "success", "1")
    return {"order_id": order_id, "trade_no": trade_no, "paid": paid}
