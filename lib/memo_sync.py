"""Debounced background RAG refresh after memo writes."""

from __future__ import annotations

import threading
from pathlib import Path

from .config import wiki_root

_lock = threading.Lock()
_timer: threading.Timer | None = None
DEBOUNCE_SEC = 1.2


def schedule_memo_rag_refresh(root: Path | None = None) -> None:
    """Coalesce rapid memo saves into one background RAG rebuild."""
    global _timer
    root = root or wiki_root()
    with _lock:
        if _timer is not None:
            _timer.cancel()
        _timer = threading.Timer(DEBOUNCE_SEC, _run_refresh, args=(root,))
        _timer.daemon = True
        _timer.start()


def _run_refresh(root: Path) -> None:
    try:
        from .ingest import refresh_rag

        refresh_rag(root)
    except Exception:
        pass
