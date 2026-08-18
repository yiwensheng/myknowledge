"""License server configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def port() -> int:
    try:
        return int(_env("LICENSE_PORT", "18888"))
    except ValueError:
        return 18888


def db_path() -> Path:
    raw = _env("LICENSE_DB", "license.db")
    p = Path(raw)
    return p if p.is_absolute() else ROOT / p


def jwt_secret() -> str:
    return _env("LICENSE_JWT_SECRET", "dev-insecure-change-me")


def admin_key() -> str:
    return _env("LICENSE_ADMIN_KEY", "dev-admin")


def plan_prices(product: str = "yizhi") -> dict[str, float]:
    """产品定价：yizhi=易知，zhouyi=周易卦象。"""
    prod = (product or "yizhi").strip().lower()
    if prod == "zhouyi":
        try:
            month = float(_env("LICENSE_PRICE_ZHOUYI_MONTH", "9.9"))
        except ValueError:
            month = 9.9
        try:
            year = float(_env("LICENSE_PRICE_ZHOUYI_YEAR", "39.9"))
        except ValueError:
            year = 39.9
        try:
            lifetime = float(_env("LICENSE_PRICE_ZHOUYI_LIFETIME", "99.9"))
        except ValueError:
            lifetime = 99.9
        return {"month": month, "year": year, "lifetime": lifetime}

    try:
        month = float(_env("LICENSE_PRICE_MONTH", "29"))
    except ValueError:
        month = 29.0
    try:
        year = float(_env("LICENSE_PRICE_YEAR", "299"))
    except ValueError:
        year = 299.0
    try:
        lifetime = float(_env("LICENSE_PRICE_LIFETIME", "199"))
    except ValueError:
        lifetime = 199.0
    return {"month": month, "year": year, "lifetime": lifetime}


def product_title_prefix(product: str = "yizhi") -> str:
    if (product or "").strip().lower() == "zhouyi":
        return "周易卦象"
    return "易知"


def unbind_per_year() -> int:
    try:
        return max(0, int(_env("LICENSE_UNBIND_PER_YEAR", "1")))
    except ValueError:
        return 1


def xunhupay_config() -> dict[str, str]:
    return {
        "appid": _env("XUNHUPAY_APPID"),
        "appsecret": _env("XUNHUPAY_APPSECRET"),
        "gateway": _env("XUNHUPAY_GATEWAY", "https://api.xunhupay.com/payment/do.html"),
        "notify_url": _env("XUNHUPAY_NOTIFY_URL"),
        "return_url": _env("XUNHUPAY_RETURN_URL"),
    }


def xunhupay_ssl_verify() -> bool:
    """Verify HTTPS cert when calling xunhupay. Set XUNHUPAY_SSL_VERIFY=0 if behind SSL-inspecting proxy."""
    return _env("XUNHUPAY_SSL_VERIFY", "1").lower() not in ("0", "false", "no")


def dev_mock_pay() -> bool:
    cfg = xunhupay_config()
    if cfg["appid"] and cfg["appsecret"]:
        return False
    return _env("LICENSE_DEV_MOCK_PAY", "1").lower() in ("1", "true", "yes")


def feedback_enabled() -> bool:
    return _env("FEEDBACK_ENABLED", "1").lower() not in ("0", "false", "no")
