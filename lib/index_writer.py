"""Per-wiki-root lock and debounced index sync for RAG mutations."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from .config import wiki_root

log = logging.getLogger("myknowledge.index_writer")

_meta_lock = threading.Lock()
_locks: dict[str, threading.Lock] = {}
_building: set[str] = set()
_debounce_timers: dict[str, threading.Timer] = {}
_debounce_pending: set[str] = set()

T = TypeVar("T")

DEBOUNCE_SECONDS = 6.0


def index_lock(root: Path | None = None) -> threading.Lock:
    root = root or wiki_root()
    key = str(root.resolve())
    with _meta_lock:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]


def with_index_lock(root: Path | None, fn: Callable[[], T]) -> T:
    with index_lock(root):
        return fn()


def is_index_building(root: Path | None = None) -> bool:
    root = root or wiki_root()
    key = str(root.resolve())
    with _meta_lock:
        return key in _building


def schedule_index_build(root: Path | None = None) -> None:
    """Background full index build when index file is missing."""
    root = root or wiki_root()
    key = str(root.resolve())
    with _meta_lock:
        if key in _building:
            return
        _building.add(key)

    def _run() -> None:
        try:
            from .ingest import sync_all

            with_index_lock(root, lambda: sync_all(root))
            log.info("background index build finished for %s", key)
        except Exception:
            log.exception("background index build failed")
        finally:
            with _meta_lock:
                _building.discard(key)

    threading.Thread(target=_run, name=f"index-build-{key[-8:]}", daemon=True).start()


def schedule_debounced_sync(root: Path | None = None, delay: float = DEBOUNCE_SECONDS) -> None:
    """Coalesce multiple watcher ingest events into one sync_all."""
    root = root or wiki_root()
    key = str(root.resolve())
    with _meta_lock:
        _debounce_pending.add(key)
        old = _debounce_timers.pop(key, None)
        if old:
            old.cancel()

        def _fire() -> None:
            with _meta_lock:
                _debounce_timers.pop(key, None)
                if key not in _debounce_pending:
                    return
                _debounce_pending.discard(key)
            try:
                from .ingest import sync_all

                with_index_lock(root, lambda: sync_all(root))
                log.info("debounced sync_all completed for %s", key)
            except Exception:
                log.exception("debounced sync_all failed")

        timer = threading.Timer(delay, _fire)
        _debounce_timers[key] = timer
        timer.daemon = True
        timer.start()


def run_sync_now(root: Path | None = None) -> int:
    from .ingest import sync_all

    return with_index_lock(root, lambda: sync_all(root or wiki_root()))
