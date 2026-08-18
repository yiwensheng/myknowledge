"""Background jobs for linked external directory RAG indexing."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .config import wiki_root
from .linked_dirs import mark_path_indexed

BEIJING = timezone(timedelta(hours=8))
_jobs: dict[str, "LinkedDirIndexJob"] = {}
_lock = threading.Lock()
_MAX_JOBS = 12


@dataclass
class LinkedDirIndexJob:
    id: str
    status: str  # queued | running | done | failed
    phase: str = "queued"  # scan | extract | embed | done
    paths: list[str] = field(default_factory=list)
    total_files: int = 0
    done_files: int = 0
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
            "paths": list(self.paths),
            "total_files": self.total_files,
            "done_files": self.done_files,
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
        if self.phase == "embed" and self.total_files > 0:
            return min(99, int(85 + 14 * self.done_files / max(1, self.total_files)))
        if self.total_files <= 0:
            return 5 if self.status == "running" else 0
        return min(85, int(85 * self.done_files / self.total_files))


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


def path_index_status(path: str) -> dict[str, Any] | None:
    try:
        norm = str(Path(path).expanduser().resolve())
    except OSError:
        norm = path
    with _lock:
        for job in _jobs.values():
            if job.status not in ("queued", "running"):
                continue
            if not job.paths:
                return job.to_dict()
            for p in job.paths:
                try:
                    if str(Path(p).expanduser().resolve()) == norm:
                        return job.to_dict()
                except OSError:
                    continue
    return None


def start_linked_dir_index(target_paths: list[str] | None = None) -> dict[str, Any]:
    with _lock:
        for job in _jobs.values():
            if job.status in ("queued", "running"):
                return {"job_id": job.id, "already_running": True, "job": job.to_dict()}

        job_id = uuid.uuid4().hex[:12]
        paths = [str(p) for p in (target_paths or []) if str(p).strip()]
        job = LinkedDirIndexJob(
            id=job_id,
            status="queued",
            paths=paths,
            started_at=_now_iso(),
        )
        _jobs[job_id] = job
        _trim_jobs()

    threading.Thread(target=_run_job, args=(job_id,), name=f"linked-dir-index-{job_id}", daemon=True).start()
    return {"job_id": job_id, "already_running": False, "job": get_job(job_id)}


def _run_job(job_id: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job.status = "running"
        job.phase = "scan"

    root = wiki_root()
    paths_snapshot = list(job.paths)

    def progress(phase: str, total: int, done: int, current: str) -> None:
        with _lock:
            j = _jobs.get(job_id)
            if not j:
                return
            j.phase = phase
            j.total_files = total
            j.done_files = done
            j.current = current

    try:
        from .rag import reindex_linked_dirs

        path_objs: list[Path] | None = None
        if paths_snapshot:
            path_objs = [Path(p).expanduser().resolve() for p in paths_snapshot]

        n = reindex_linked_dirs(path_objs, root=root, progress=progress)

        with _lock:
            j = _jobs.get(job_id)
            if not j:
                return
            j.rag_chunks = n
            j.phase = "done"
            j.status = "done"
            j.finished_at = _now_iso()
            j.current = ""
            if j.total_files > 0:
                j.done_files = j.total_files

        if paths_snapshot:
            for p in paths_snapshot:
                mark_path_indexed(p)
        else:
            from .linked_dirs import mark_all_indexed

            mark_all_indexed()
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
