"""Background upload / ingest jobs — parallel extract, single index rebuild."""

from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import load_dotenv, wiki_root
from .ingest import _ingest_workers, ingest_file, sync_all_after_upload

BEIJING = timezone(timedelta(hours=8))
_jobs: dict[str, "UploadJob"] = {}
_lock = threading.Lock()
_MAX_JOBS = 20
_INDEX_COALESCE_SEC = 1.5
_upload_index_batches: dict[str, dict[str, Any]] = {}
_upload_index_meta = threading.Lock()


@dataclass
class UploadJob:
    id: str
    status: str  # queued | running | done | failed
    total: int
    done: int = 0
    phase: str = "ingest"  # ingest | index
    items: list[dict[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    rag_chunks: int = 0
    started_at: str = ""
    finished_at: str = ""
    current: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "total": self.total,
            "done": self.done,
            "phase": self.phase,
            "items": list(self.items),
            "errors": list(self.errors),
            "rag_chunks": self.rag_chunks,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "current": self.current,
        }


def batch_defer_analyze() -> bool:
    """Batch uploads skip LLM analysis by default for speed."""
    load_dotenv()
    raw = os.environ.get("MYKNOWLEDGE_INGEST_BATCH_ANALYZE", "0").strip().lower()
    return raw in ("1", "true", "yes")


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
        return [
            j.to_dict()
            for j in _jobs.values()
            if j.status in ("queued", "running")
        ]


def _run_coalesced_index(key: str, root: Path) -> None:
    waiters: list[tuple[str, threading.Event]] = []
    rag_chunks = 0
    err: str | None = None
    try:
        with _upload_index_meta:
            batch = _upload_index_batches.pop(key, None)
        if not batch:
            return
        waiters = list(batch.get("waiters") or [])
        rag_chunks = sync_all_after_upload(root)
        try:
            from .docubrowser_bridge import maybe_defer_rescan

            maybe_defer_rescan(root)
        except Exception:
            pass
    except Exception as exc:
        err = str(exc)
    finally:
        for job_id, ev in waiters:
            with _lock:
                j = _jobs.get(job_id)
                if j:
                    if err:
                        j.errors.append(f"检索库更新失败: {err}")
                    else:
                        j.rag_chunks = rag_chunks
            ev.set()


def _coalesced_sync_all(job_id: str, root: Path) -> int:
    """Merge concurrent upload jobs into one index rebuild."""
    key = str(root.resolve())
    ev = threading.Event()
    with _upload_index_meta:
        batch = _upload_index_batches.setdefault(key, {"waiters": [], "timer": None})
        batch["waiters"].append((job_id, ev))
        old = batch.get("timer")
        if old:
            old.cancel()

        def _fire() -> None:
            _run_coalesced_index(key, root)

        timer = threading.Timer(_INDEX_COALESCE_SEC, _fire)
        timer.daemon = True
        timer.start()
        batch["timer"] = timer

    with _lock:
        j = _jobs.get(job_id)
        if j:
            j.phase = "index"
            j.current = "正在更新检索库…"

    if not ev.wait(timeout=120):
        with _lock:
            j = _jobs.get(job_id)
            if j:
                j.errors.append("检索库更新超时")
        return 0
    with _lock:
        j = _jobs.get(job_id)
        return int(j.rag_chunks) if j else 0


def _process_one(
    tmp_path: Path,
    original_name: str | None,
    root: Path,
    *,
    defer_analyze: bool,
) -> tuple[str | None, str | None]:
    """Returns (ingested_rel, error_message)."""
    try:
        rel = ingest_file(
            tmp_path,
            root,
            move_inbox=False,
            original_filename=original_name,
            defer_index=True,
            defer_analyze=defer_analyze,
        )
        if not rel:
            return None, f"{original_name or tmp_path.name}: 无法入库"
        return rel, None
    except Exception as exc:
        return None, f"{original_name or tmp_path.name}: {exc}"
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


def _run_job(job_id: str, specs: list[tuple[Path, str | None]], root: Path) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job.status = "running"
        job.started_at = _now_iso()

    defer_analyze = not batch_defer_analyze()
    workers = _ingest_workers()
    done_items: list[str] = []
    errors: list[str] = []

    def mark_progress(name: str, delta_done: int = 0) -> None:
        with _lock:
            j = _jobs.get(job_id)
            if not j:
                return
            j.done += delta_done
            if name:
                j.current = name

    try:
        if workers <= 1 or len(specs) < 2:
            for tmp_path, orig in specs:
                mark_progress(orig or tmp_path.name)
                rel, err = _process_one(tmp_path, orig, root, defer_analyze=defer_analyze)
                if rel:
                    done_items.append(rel)
                    with _lock:
                        j = _jobs.get(job_id)
                        if j:
                            j.items.append({"name": orig or tmp_path.name, "ingested": rel})
                if err:
                    errors.append(err)
                mark_progress("", 1)
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = {
                    pool.submit(
                        _process_one,
                        tmp_path,
                        orig,
                        root,
                        defer_analyze=defer_analyze,
                    ): (tmp_path, orig)
                    for tmp_path, orig in specs
                }
                for fut in as_completed(futs):
                    tmp_path, orig = futs[fut]
                    mark_progress(orig or tmp_path.name)
                    try:
                        rel, err = fut.result()
                    except Exception as exc:
                        rel, err = None, f"{orig or tmp_path.name}: {exc}"
                    if rel:
                        done_items.append(rel)
                        with _lock:
                            j = _jobs.get(job_id)
                            if j:
                                j.items.append({"name": orig or tmp_path.name, "ingested": rel})
                    if err:
                        errors.append(err)
                    mark_progress("", 1)

        rag_chunks = 0
        if done_items:
            rag_chunks = _coalesced_sync_all(job_id, root)

        with _lock:
            j = _jobs.get(job_id)
            if not j:
                return
            j.rag_chunks = rag_chunks
            j.errors = errors
            j.status = "failed" if errors and not done_items else "done"
            j.finished_at = _now_iso()
            j.current = ""
            if j.done < j.total:
                j.done = j.total
    except Exception as exc:
        with _lock:
            j = _jobs.get(job_id)
            if j:
                j.status = "failed"
                j.errors.append(str(exc))
                j.finished_at = _now_iso()
                j.current = ""


def enqueue_upload_job(
    specs: list[tuple[Path, str | None]],
    root: Path | None = None,
) -> str:
    """Start background ingest; returns job id immediately."""
    if not specs:
        raise ValueError("no files")
    root = root or wiki_root()
    job_id = uuid.uuid4().hex[:16]
    job = UploadJob(id=job_id, status="queued", total=len(specs))
    with _lock:
        _jobs[job_id] = job
        _trim_jobs()

    threading.Thread(
        target=_run_job,
        args=(job_id, specs, root),
        daemon=True,
        name=f"upload-job-{job_id}",
    ).start()
    return job_id
