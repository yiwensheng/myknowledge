"""Local license state (.license/state.json)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import wiki_root

BEIJING = timezone(timedelta(hours=8))
LICENSE_DIR = ".license"
STATE_FILE = "state.json"
INSTALL_FILE = "install.json"
OFFLINE_GRACE_DAYS = 7
TRIAL_DAYS = 30


def license_dir(root: Path | None = None) -> Path:
    d = (root or wiki_root()) / LICENSE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def state_path(root: Path | None = None) -> Path:
    return license_dir(root) / STATE_FILE


def load_state(root: Path | None = None) -> dict:
    p = state_path(root)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(data: dict, root: Path | None = None) -> None:
    p = state_path(root)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def install_path(root: Path | None = None) -> Path:
    return license_dir(root) / INSTALL_FILE


def ensure_install_recorded(root: Path | None = None) -> dict:
    """Record first-run install date (Beijing calendar day) for 30-day trial."""
    p = install_path(root)
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("installed_at"):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    data = {"installed_at": datetime.now(BEIJING).strftime("%Y-%m-%d")}
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def trial_status(root: Path | None = None) -> dict:
    """Natural calendar days from install date; unused days still count."""
    data = ensure_install_recorded(root)
    try:
        installed = datetime.strptime(str(data["installed_at"]), "%Y-%m-%d").date()
    except ValueError:
        installed = datetime.now(BEIJING).date()
    today = datetime.now(BEIJING).date()
    elapsed = max(0, (today - installed).days)
    days_left = max(0, TRIAL_DAYS - elapsed)
    return {
        "installed_at": data.get("installed_at", ""),
        "elapsed_days": elapsed,
        "days_left": days_left,
        "active": elapsed < TRIAL_DAYS,
        "trial_days": TRIAL_DAYS,
    }


def clear_state(root: Path | None = None) -> None:
    p = state_path(root)
    if p.is_file():
        p.unlink()


def beijing_now_iso() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%dT%H:%M:%S%z")


def parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(s.replace("+0800", "+08:00"), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=BEIJING)
            return dt
        except ValueError:
            continue
    return None


def update_from_activation(
    *,
    token: str,
    device_id: str,
    expires_at: str,
    plan: str,
    license_id: str,
    root: Path | None = None,
) -> None:
    now = beijing_now_iso()
    save_state(
        {
            "token": token,
            "device_id": device_id,
            "expires_at": expires_at,
            "plan": plan,
            "license_id": license_id,
            "last_online_ok_at": now,
        },
        root,
    )


def touch_online_ok(token: str | None = None, expires_at: str | None = None, root: Path | None = None) -> None:
    st = load_state(root)
    if not st:
        return
    st["last_online_ok_at"] = beijing_now_iso()
    if token:
        st["token"] = token
    if expires_at:
        st["expires_at"] = expires_at
    save_state(st, root)


def offline_grace_exceeded(state: dict) -> bool:
    last = parse_iso(str(state.get("last_online_ok_at") or ""))
    if not last:
        return True
    return datetime.now(BEIJING) - last > timedelta(days=OFFLINE_GRACE_DAYS)


def subscription_expired(state: dict) -> bool:
    if str(state.get("plan") or "") == "lifetime":
        return False
    exp = parse_iso(str(state.get("expires_at") or ""))
    if not exp:
        return True
    return datetime.now(BEIJING) > exp
