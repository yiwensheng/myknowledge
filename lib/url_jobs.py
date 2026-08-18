"""Background jobs for URL fetch + wiki ingest."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .config import wiki_root

BEIJING = timezone(timedelta(hours=8))
_jobs: dict[str, "UrlIngestJob"] = {}
_lock = threading.Lock()
_MAX_JOBS = 16

_PHASE_PCT = {
    "queued": 0,
    "cache": 8,
    "fetch": 35,
    "analyze": 62,
    "save": 78,
    "index": 92,
    "done": 100,
}


@dataclass
class UrlIngestJob:
    id: str
    status: str  # queued | running | done | failed
    phase: str = "queued"
    url: str = ""
    force: bool = False
    current: str = ""
    title: str = ""
    method: str = ""
    wiki_page: str = ""
    localized: str = ""
    duplicate: bool = False
    rag_chunks: int = 0
    quality_ok: bool = True
    quality_warning: str = ""
    error: str = ""
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "phase": self.phase,
            "url": self.url,
            "force": self.force,
            "current": self.current,
            "title": self.title,
            "method": self.method,
            "wiki_page": self.wiki_page,
            "localized": self.localized,
            "duplicate": self.duplicate,
            "rag_chunks": self.rag_chunks,
            "quality_ok": self.quality_ok,
            "quality_warning": self.quality_warning,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "progress_pct": self.progress_pct(),
        }

    def progress_pct(self) -> int:
        if self.status == "done":
            return 100
        if self.status == "failed":
            return _PHASE_PCT.get(self.phase, 0)
        return _PHASE_PCT.get(self.phase, 5)


def _now_iso() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%dT%H:%M:%S%z")


def _trim_jobs() -> None:
    if len(_jobs) <= _MAX_JOBS:
        return
    finished = sorted(
        ((jid, j) for jid, j in _jobs.items() if j.status in ("done", "failed")),
        key=lambda x: x[1].finished_at or "",
    )
    for jid, _ in finished[: max(0, len(_jobs) - _MAX_JOBS)]:
        _jobs.pop(jid, None)


def get_job(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        return job.to_dict() if job else None


def list_active_jobs() -> list[dict[str, Any]]:
    with _lock:
        return [j.to_dict() for j in _jobs.values() if j.status in ("queued", "running")]


def start_url_ingest_job(url: str, *, force: bool = False) -> dict[str, Any]:
    url = url.strip()
    if not url:
        raise ValueError("请提供网页地址")
    with _lock:
        for job in _jobs.values():
            if job.status in ("queued", "running"):
                return {"job_id": job.id, "already_running": True, "job": job.to_dict()}

        job_id = uuid.uuid4().hex[:12]
        job = UrlIngestJob(
            id=job_id,
            status="queued",
            url=url,
            force=force,
            started_at=_now_iso(),
        )
        _jobs[job_id] = job
        _trim_jobs()

    threading.Thread(target=_run_job, args=(job_id,), name=f"url-ingest-{job_id}", daemon=True).start()
    return {"job_id": job_id, "already_running": False, "job": get_job(job_id)}


def _run_job(job_id: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job.status = "running"

    root = wiki_root()
    url = job.url
    force = job.force

    def progress(phase: str, message: str) -> None:
        with _lock:
            j = _jobs.get(job_id)
            if not j:
                return
            j.phase = phase
            j.current = message

    try:
        from .url_ingest import ingest_url

        result = ingest_url(url, root=root, force=force, progress=progress)

        with _lock:
            j = _jobs.get(job_id)
            if not j:
                return
            j.title = str(result.get("title") or "")
            j.method = str(result.get("method") or "")
            j.wiki_page = str(result.get("wiki_page") or "")
            j.localized = str(result.get("localized") or "")
            j.duplicate = bool(result.get("duplicate"))
            j.rag_chunks = int(result.get("rag_chunks") or 0)
            j.quality_ok = bool(result.get("quality_ok", True))
            j.quality_warning = str(result.get("quality_warning") or "")
            j.phase = "done"
            j.status = "done"
            j.finished_at = _now_iso()
            j.current = "已完成" if not j.duplicate else "此前已保存"
            if result.get("quality_warning"):
                j.current = str(result.get("quality_warning"))

        try:
            from .docubrowser_bridge import maybe_defer_rescan

            maybe_defer_rescan(root)
        except Exception:
            pass
    except Exception as exc:
        with _lock:
            j = _jobs.get(job_id)
            if j:
                j.status = "failed"
                j.error = str(exc)
                j.finished_at = _now_iso()
                j.current = ""


def on_job_finished(callback: Callable[[str], None] | None = None) -> None:
    if callback:
        callback("")
