"""Remote version check for 易知 desktop app."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from .config import load_dotenv

_VERSION_RE = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def _parse_version(raw: str) -> tuple[int, int, int]:
    m = _VERSION_RE.match(str(raw or "").strip())
    if not m:
        return (0, 0, 0)
    parts = [m.group(1), m.group(2) or "0", m.group(3) or "0"]
    return tuple(int(p) for p in parts)


def _version_lt(a: str, b: str) -> bool:
    return _parse_version(a) < _parse_version(b)


def _fetch_update_manifest(url: str, timeout: float = 12.0) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Yizhi-UpdateCheck/1.0", "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8-sig", errors="replace")
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("更新源返回格式无效")
    return data


def _normalize_update_url(raw: str) -> str:
    url = str(raw or "").strip()
    if not url:
        return ""
    if "TrimEnd" in url:
        return "https://www.yzwhysxx.cn/yizhi/latest.json"
    return url


def check_for_update(app_version: str = "") -> dict[str, Any]:
    load_dotenv()
    current = (app_version or os.environ.get("MYKNOWLEDGE_APP_VERSION") or "0.0.0").strip()
    feed_url = _normalize_update_url(os.environ.get("MYKNOWLEDGE_UPDATE_URL", ""))
    checked_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")

    base: dict[str, Any] = {
        "ok": True,
        "current_version": current,
        "latest_version": current,
        "update_available": False,
        "download_url": "",
        "release_notes": "",
        "checked_at": checked_at,
        "feed_configured": bool(feed_url),
    }

    if not feed_url:
        base["message"] = f"当前版本 {current}（未配置远程更新源）"
        return base

    try:
        manifest = _fetch_update_manifest(feed_url)
    except urllib.error.URLError as e:
        return {
            **base,
            "ok": False,
            "message": f"无法连接更新服务器：{e.reason if hasattr(e, 'reason') else e}",
        }
    except Exception as e:
        return {
            **base,
            "ok": False,
            "message": f"检查更新失败：{e}",
        }

    latest = str(manifest.get("latest_version") or manifest.get("version") or "").strip()
    if not latest:
        return {
            **base,
            "ok": False,
            "message": "更新源未提供 version 字段",
        }

    download_url = str(manifest.get("download_url") or manifest.get("url") or "").strip()
    notes = str(manifest.get("release_notes") or manifest.get("notes") or "").strip()
    recalled = manifest.get("recalled_versions") or manifest.get("yanked_versions") or []
    if not isinstance(recalled, list):
        recalled = []
    recalled = [str(v).strip() for v in recalled if str(v).strip()]
    recalled_message = str(manifest.get("recalled_message") or "").strip()
    update_available = _version_lt(current, latest)
    current_recalled = current in recalled

    if current_recalled:
        message = recalled_message or (
            f"当前版本 {current} 已撤回，请立即升级到 {latest}"
        )
        # 撤回版视为必须升级（即使误判版本高低也提示）
        if latest and current != latest:
            update_available = True
    elif update_available:
        message = f"发现新版本 {latest}（当前 {current}）"
    else:
        message = f"当前已是最新版本（{current}）"

    return {
        **base,
        "latest_version": latest,
        "update_available": update_available,
        "download_url": download_url,
        "release_notes": notes,
        "recalled_versions": recalled,
        "current_recalled": current_recalled,
        "recalled_message": recalled_message if current_recalled else "",
        "message": message,
    }
