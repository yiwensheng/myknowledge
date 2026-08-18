"""Persist feedback on license-server disk (inbox) before/alongside mail."""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .config import db_path

_flush_lock = threading.Lock()
_flush_started = False


def inbox_dir() -> Path:
    d = db_path().resolve().parent / "feedback_inbox"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_feedback(
    *,
    html: str,
    subject: str,
    contact: str = "",
    app_version: str = "",
    device_id: str = "",
    client_ip: str = "",
) -> dict[str, Any]:
    from datetime import datetime, timedelta, timezone

    from . import db

    fid = uuid.uuid4().hex
    beijing = timezone(timedelta(hours=8))
    created_at = datetime.now(beijing).strftime("%Y-%m-%d %H:%M:%S")
    item: dict[str, Any] = {
        "id": fid,
        "created_at": created_at,
        "html": html,
        "subject": subject or "易知用户反馈",
        "contact": contact or "",
        "app_version": app_version or "",
        "device_id": device_id or "",
        "client_ip": client_ip or "",
        "mailed": False,
        "mail_method": "",
        "mail_error": "",
        "mailed_at": 0,
    }
    path = inbox_dir() / f"{fid}.json"
    path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
    # 有网提交时固化到 SQLite，运营台可查
    try:
        db.insert_feedback(
            feedback_id=fid,
            html=html,
            subject=item["subject"],
            contact=item["contact"],
            app_version=item["app_version"],
            device_id=item["device_id"],
            client_ip=item["client_ip"],
            created_at=created_at,
        )
    except Exception:
        pass
    return item


def _item_path(fid: str) -> Path:
    return inbox_dir() / f"{fid}.json"


def update_mail_status(
    fid: str,
    *,
    mailed: bool,
    method: str = "",
    error: str = "",
) -> None:
    path = _item_path(fid)
    if path.is_file():
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
            item["mailed"] = bool(mailed)
            item["mail_method"] = method or ""
            item["mail_error"] = (error or "")[:500]
            if mailed:
                item["mailed_at"] = time.time()
            path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        except (json.JSONDecodeError, OSError):
            pass
    try:
        from . import db

        db.update_feedback_mail(fid, mailed=mailed, method=method, error=error)
    except Exception:
        pass


def list_unmailed(*, limit: int = 30) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in sorted(inbox_dir().glob("*.json"), key=lambda p: p.stat().st_mtime):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if item.get("mailed"):
            continue
        items.append(item)
        if len(items) >= limit:
            break
    return items


def try_mail_item(item: dict[str, Any], *, timeout_sec: float = 20.0) -> tuple[bool, str, str]:
    """Returns (ok, method, error). Never hangs longer than timeout_sec."""
    from .feedback_mail import send_feedback_email

    subject = str(item.get("subject") or "易知用户反馈")
    if item.get("app_version"):
        subject = f"{subject} · v{item['app_version']}"
    meta_lines = [
        f"id={item.get('id') or '-'}",
        f"app_version={item.get('app_version') or '-'}",
        f"device_id={item.get('device_id') or '-'}",
        f"contact={item.get('contact') or '-'}",
        f"ip={item.get('client_ip') or '-'}",
    ]
    result: dict[str, Any] = {"ok": False, "method": "", "error": ""}

    def _run() -> None:
        try:
            method = send_feedback_email(
                subject=subject,
                html=str(item.get("html") or ""),
                reply_to=str(item.get("contact") or "").strip(),
                meta_text="\n".join(meta_lines),
            )
            result["ok"] = True
            result["method"] = method
        except Exception as exc:  # noqa: BLE001
            result["error"] = str(exc)

    t = threading.Thread(target=_run, name="feedback-mail", daemon=True)
    t.start()
    t.join(timeout=timeout_sec)
    if t.is_alive():
        return False, "", f"发信超时（>{int(timeout_sec)}s）"
    if result["ok"]:
        return True, str(result["method"]), ""
    return False, "", str(result["error"] or "发信失败")


def flush_unmailed(*, limit: int = 10) -> dict[str, Any]:
    with _flush_lock:
        sent = 0
        failed = 0
        last_error = ""
        for item in list_unmailed(limit=limit):
            fid = str(item.get("id") or "")
            ok, method, err = try_mail_item(item, timeout_sec=25.0)
            if ok:
                update_mail_status(fid, mailed=True, method=method)
                sent += 1
            else:
                update_mail_status(fid, mailed=False, error=err)
                failed += 1
                last_error = err
        return {"sent": sent, "failed": failed, "last_error": last_error}


def start_feedback_mail_flusher() -> None:
    global _flush_started
    if _flush_started:
        return
    _flush_started = True

    def _loop() -> None:
        time.sleep(15)
        while True:
            try:
                if list_unmailed(limit=1):
                    flush_unmailed(limit=5)
            except Exception:
                pass
            time.sleep(180)

    threading.Thread(target=_loop, name="license-feedback-flush", daemon=True).start()
