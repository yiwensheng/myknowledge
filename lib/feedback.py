"""Client-side feedback: local queue + POST to license-server /feedback."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from .config import load_dotenv, wiki_root
from .device_id import compute_device_id

_flush_lock = threading.Lock()
_flush_started = False


def _queue_dir() -> Path:
    d = wiki_root() / ".feedback_queue"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _feedback_url() -> str:
    load_dotenv()
    explicit = os.environ.get("MYKNOWLEDGE_FEEDBACK_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    server = os.environ.get("MYKNOWLEDGE_LICENSE_SERVER", "").strip().rstrip("/")
    if not server:
        return ""
    return f"{server}/feedback"


def _app_version() -> str:
    try:
        from .commercial_links import app_version  # type: ignore

        return str(app_version() or "")
    except Exception:
        pass
    # electron package.json sibling
    try:
        from .config import ROOT

        pkg = ROOT / "electron" / "package.json"
        if pkg.is_file():
            data = json.loads(pkg.read_text(encoding="utf-8"))
            return str(data.get("version") or "")
    except Exception:
        pass
    return ""


def enqueue_feedback(
    *,
    html: str,
    subject: str = "",
    contact: str = "",
) -> dict[str, Any]:
    item = {
        "id": uuid.uuid4().hex,
        "created_at": time.time(),
        "html": html,
        "subject": subject or "易知用户反馈",
        "contact": contact or "",
        "app_version": _app_version(),
        "device_id": compute_device_id(),
    }
    path = _queue_dir() / f"{item['id']}.json"
    path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
    sent = False
    err = ""
    mailed = False
    try:
        result = flush_pending(limit=1, only_id=item["id"])
    except Exception as exc:
        err = str(exc)
        result = {}
    sent = bool(result.get("sent"))
    err = str(result.get("last_error") or err or "")
    remote = result.get("last_remote") or {}
    mailed = bool(remote.get("mailed"))
    return {
        "ok": True,
        "id": item["id"],
        "queued": True,
        "sent": sent,
        "mailed": mailed,
        "pending": pending_count(),
        "error": err if not sent else "",
        "mail_error": str(remote.get("mail_error") or "") if sent and not mailed else "",
    }


def pending_count() -> int:
    return len(list(_queue_dir().glob("*.json")))


def _post_remote(item: dict[str, Any]) -> dict[str, Any]:
    url = _feedback_url()
    if not url:
        raise RuntimeError("未配置 MYKNOWLEDGE_LICENSE_SERVER / MYKNOWLEDGE_FEEDBACK_URL")
    payload = json.dumps(
        {
            "html": item.get("html") or "",
            "subject": item.get("subject") or "易知用户反馈",
            "contact": item.get("contact") or "",
            "app_version": item.get("app_version") or "",
            "device_id": item.get("device_id") or "",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        # 限时：服务端若挂起，尽快回落本地队列
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"HTTP {e.code}: {detail or e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络不可用: {e.reason}") from e
    except TimeoutError as e:
        raise RuntimeError("网络超时：已保留本地队列") from e
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        data = {}
    if not data.get("ok", True):
        raise RuntimeError(str(data.get("detail") or data or "服务器拒绝"))
    # 服务端已落盘即视为投递成功（邮件可能异步补发）
    if data.get("stored") is False and data.get("mailed") is False:
        raise RuntimeError(str(data.get("mail_error") or "服务器未接收"))
    return data


def flush_pending(*, limit: int = 20, only_id: str | None = None) -> dict[str, Any]:
    with _flush_lock:
        files = sorted(_queue_dir().glob("*.json"), key=lambda p: p.stat().st_mtime)
        sent = 0
        failed = 0
        last_error = ""
        last_remote: dict[str, Any] = {}
        for path in files:
            if only_id and path.stem != only_id:
                continue
            if sent + failed >= limit:
                break
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
                last_remote = _post_remote(item)
                path.unlink(missing_ok=True)
                sent += 1
            except Exception as exc:
                failed += 1
                last_error = str(exc)
                if only_id:
                    break
        return {
            "sent": sent,
            "failed": failed,
            "pending": pending_count(),
            "last_error": last_error,
            "endpoint": _feedback_url() or "",
            "last_remote": last_remote,
        }


def start_feedback_flusher() -> None:
    global _flush_started
    if _flush_started:
        return
    _flush_started = True

    def _loop() -> None:
        time.sleep(8)
        while True:
            try:
                if pending_count():
                    flush_pending()
            except Exception:
                pass
            time.sleep(120)

    threading.Thread(target=_loop, name="yizhi-feedback-flush", daemon=True).start()
