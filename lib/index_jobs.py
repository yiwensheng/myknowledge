"""Background jobs for full RAG index rebuild (sync_all)."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import wiki_root
from .index_writer import run_sync_now

BEIJING = timezone(timedelta(hours=8))
_jobs: dict[str, "IndexJob"] = {}
_lock = threading.Lock()
_MAX_JOBS = 8


@dataclass
class IndexJob:
    id: str
    status: str
    phase: str = "queued"
    current: str = ""
    rag_chunks: int = 0
    error: str = ""
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "phase": self.phase,
            "current": self.current,
            "rag_chunks": self.rag_chunks,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "progress_pct": self.progress_pct(),
        }

    def progress_pct(self) -> int:
        if self.status == "done":
            return 100
        if self.phase == "embed":
            return 85
        if self.phase == "rebuild":
            return 45
        if self.status == "running":
            return 15
        return 0


def _now_iso() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%dT%H:%M:%S%z")


def get_job(job_id: str) -> dict[str, Any] | None:
    with _lock:
        j = _jobs.get(job_id)
        return j.to_dict() if j else None


def list_active_jobs() -> list[dict[str, Any]]:
    with _lock:
        return [j.to_dict() for j in _jobs.values() if j.status in ("queued", "running")]


def start_index_job() -> dict[str, Any]:
    with _lock:
        for job in _jobs.values():
            if job.status in ("queued", "running"):
                return {"job_id": job.id, "already_running": True, "job": job.to_dict()}
        job_id = uuid.uuid4().hex[:12]
        job = IndexJob(id=job_id, status="queued", started_at=_now_iso())
        _jobs[job_id] = job

    threading.Thread(target=_run, args=(job_id,), name=f"index-job-{job_id}", daemon=True).start()
    return {"job_id": job_id, "already_running": False, "job": get_job(job_id)}


def _run(job_id: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job.status = "running"
        job.phase = "rebuild"
        job.current = "正在重建检索库…"

    root = wiki_root()
    try:
        n = run_sync_now(root)
        with _lock:
            j = _jobs.get(job_id)
            if not j:
                return
            j.rag_chunks = n
            j.phase = "done"
            j.status = "done"
            j.current = f"共 {n} 段"
            j.finished_at = _now_iso()
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
