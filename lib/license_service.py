"""License verification, remote API, and gate."""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from typing import Any

from .config import load_dotenv, wiki_root
from .device_id import compute_device_id
from .license_jwt import verify_token
from .license_local import (
    clear_state,
    load_state,
    offline_grace_exceeded,
    subscription_expired,
    touch_online_ok,
    trial_status,
    update_from_activation,
)

_heartbeat_lock = threading.Lock()
_last_heartbeat_attempt = 0.0
HEARTBEAT_INTERVAL_SEC = 24 * 3600


def license_config() -> dict[str, str | bool]:
    load_dotenv()
    server = os.environ.get("MYKNOWLEDGE_LICENSE_SERVER", "").strip().rstrip("/")
    secret = os.environ.get("MYKNOWLEDGE_LICENSE_JWT_SECRET", "").strip()
    required_raw = os.environ.get("MYKNOWLEDGE_LICENSE_REQUIRED", "").strip().lower()
    if required_raw in ("0", "false", "no"):
        required = False
    elif required_raw in ("1", "true", "yes"):
        required = True
    else:
        required = bool(server)
    return {
        "server": server,
        "jwt_secret": secret,
        "required": required,
    }


def get_device_id() -> str:
    return compute_device_id()


def _post_json(url: str, body: dict, timeout: float = 15.0) -> dict[str, Any]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            detail = json.loads(raw)
            if isinstance(detail, dict) and "detail" in detail:
                raise RuntimeError(str(detail["detail"])) from exc
        except json.JSONDecodeError:
            pass
        raise RuntimeError(raw or str(exc)) from exc


def _get_json(url: str, timeout: float = 15.0) -> dict[str, Any]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_plans() -> dict[str, Any]:
    cfg = license_config()
    server = str(cfg["server"])
    if not server:
        return {"plans": []}
    return _get_json(f"{server}/license/plans")


def create_order(plan: str, device_id: str | None = None) -> dict[str, Any]:
    cfg = license_config()
    server = str(cfg["server"])
    if not server:
        raise RuntimeError("未配置授权服务器")
    did = device_id or get_device_id()
    return _post_json(f"{server}/license/create-order", {"plan": plan, "device_id": did})


def poll_order(order_id: str) -> dict[str, Any]:
    cfg = license_config()
    server = str(cfg["server"])
    return _get_json(f"{server}/license/order/{order_id}")


def activate_remote(
    *,
    order_id: str = "",
    code: str = "",
    device_id: str | None = None,
) -> dict[str, Any]:
    cfg = license_config()
    server = str(cfg["server"])
    did = device_id or get_device_id()
    body: dict[str, str] = {"device_id": did}
    if order_id:
        body["order_id"] = order_id
    if code:
        body["code"] = code
    result = _post_json(f"{server}/license/activate", body)
    update_from_activation(
        token=result["token"],
        device_id=did,
        expires_at=result["expires_at"],
        plan=result.get("plan", ""),
        license_id=result.get("license_id", ""),
        root=wiki_root(),
    )
    return result


def self_unbind_remote(device_id: str | None = None) -> dict[str, Any]:
    cfg = license_config()
    server = str(cfg["server"])
    st = load_state()
    token = st.get("token")
    if not token:
        raise RuntimeError("无有效授权")
    did = device_id or get_device_id()
    _post_json(f"{server}/license/self-unbind", {"token": token, "device_id": did})
    clear_state()
    return {"ok": True}


def try_heartbeat() -> bool:
    cfg = license_config()
    server = str(cfg["server"])
    if not server:
        return False
    st = load_state()
    token = st.get("token")
    if not token:
        return False
    did = get_device_id()
    try:
        result = _post_json(
            f"{server}/license/heartbeat",
            {"token": token, "device_id": did},
        )
        touch_online_ok(result.get("token"), result.get("expires_at"))
        return True
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return False
    except RuntimeError as exc:
        # 服务端 402 等会被 _post_json 转成 RuntimeError；吊销/换机不得拖垮启动
        msg = str(exc).strip().lower()
        if msg in ("license_revoked", "device_mismatch", "expired", "license_not_found"):
            clear_state()
        return False


def maybe_heartbeat_background() -> None:
    import time

    global _last_heartbeat_attempt
    with _heartbeat_lock:
        now = time.time()
        if now - _last_heartbeat_attempt < HEARTBEAT_INTERVAL_SEC:
            return
        _last_heartbeat_attempt = now
    try:
        try_heartbeat()
    except Exception:
        # 心跳失败不影响进程启动；授权门禁由 check_license 决定
        return

def check_license(force_online: bool = False) -> dict[str, Any]:
    """Return license status for UI and gate."""
    cfg = license_config()
    root = wiki_root()
    base = {
        "device_id": get_device_id(),
        "expires_at": "",
        "plan": "",
        "offline_grace_days": 7,
        "trial_days": trial_status(root).get("trial_days", 30),
        "trial_days_left": 0,
        "installed_at": "",
    }
    if not cfg["required"]:
        return {
            **base,
            "licensed": True,
            "reason": "not_required",
        }

    did = get_device_id()
    st = load_state()
    if not st.get("token"):
        trial = trial_status(root)
        if trial["active"]:
            return {
                **base,
                "licensed": True,
                "reason": "trial",
                "trial_days_left": trial["days_left"],
                "installed_at": trial["installed_at"],
            }
        return {
            **base,
            "licensed": False,
            "reason": "trial_expired",
            "trial_days_left": 0,
            "installed_at": trial["installed_at"],
        }

    if st.get("device_id") and st["device_id"] != did:
        return {
            "licensed": False,
            "reason": "device_mismatch",
            "device_id": did,
            "expires_at": st.get("expires_at", ""),
            "plan": st.get("plan", ""),
            "offline_grace_days": 7,
        }

    secret = str(cfg.get("jwt_secret") or "")
    if cfg["required"] and not secret:
        return {
            "licensed": False,
            "reason": "misconfigured",
            "device_id": did,
            "expires_at": "",
            "plan": "",
            "offline_grace_days": 7,
        }
    payload = verify_token(str(st["token"]), secret) if secret else None
    if secret and not payload:
        clear_state()
        return {
            "licensed": False,
            "reason": "invalid_token",
            "device_id": did,
            "expires_at": "",
            "plan": "",
            "offline_grace_days": 7,
        }

    if subscription_expired(st):
        return {
            "licensed": False,
            "reason": "expired",
            "device_id": did,
            "expires_at": st.get("expires_at", ""),
            "plan": st.get("plan", ""),
            "offline_grace_days": 7,
        }

    maybe_heartbeat_background()

    online_ok = False
    if force_online:
        online_ok = try_heartbeat()
        if online_ok:
            st = load_state()
    else:
        if not offline_grace_exceeded(st):
            maybe_heartbeat_background()
            st = load_state()
            online_ok = not offline_grace_exceeded(st)
        else:
            online_ok = try_heartbeat()
            if online_ok:
                st = load_state()

    if not online_ok and offline_grace_exceeded(st):
        return {
            "licensed": False,
            "reason": "offline_grace_exceeded",
            "device_id": did,
            "expires_at": st.get("expires_at", ""),
            "plan": st.get("plan", ""),
            "offline_grace_days": 7,
            "last_online_ok_at": st.get("last_online_ok_at", ""),
        }

    return {
        "licensed": True,
        "reason": "ok",
        "device_id": did,
        "expires_at": st.get("expires_at", ""),
        "plan": st.get("plan", ""),
        "offline_grace_days": 7,
        "last_online_ok_at": st.get("last_online_ok_at", ""),
    }


def require_license() -> None:
    status = check_license()
    if not status.get("licensed"):
        from fastapi import HTTPException

        reason = status.get("reason", "no_license")
        msgs = {
            "no_license": "请先激活易知订阅",
            "trial_expired": "30 天试用已结束，请订阅后继续使用",
            "expired": "订阅已到期，请续费",
            "device_mismatch": "授权与当前设备不匹配",
            "invalid_token": "授权无效，请重新激活",
            "offline_grace_exceeded": "已超过 7 天未联网校验，请连接网络后重试",
        }
        raise HTTPException(402, detail=msgs.get(reason, "未授权"))
