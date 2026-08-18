"""Poll linked external directories and refresh RAG when files change."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from .config import wiki_root
from .linked_dirs import auto_index_enabled, dir_fingerprint, linked_dir_paths, poll_seconds

log = logging.getLogger("myknowledge.linked_dir_watcher")


class LinkedDirWatcher:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or wiki_root()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._prints: dict[str, tuple[int, float]] = {}

    def _scan_once(self) -> bool:
        if not auto_index_enabled():
            return False
        changed = False
        for ext_root in linked_dir_paths():
            key = str(ext_root.resolve())
            fp = dir_fingerprint(ext_root)
            prev = self._prints.get(key)
            if prev is None:
                self._prints[key] = fp
                continue
            if fp != prev:
                self._prints[key] = fp
                changed = True
                log.info("linked dir changed: %s", key)
        if not changed:
            return False
        from .linked_dir_jobs import list_active_jobs, start_linked_dir_index

        if list_active_jobs():
            return False
        start_linked_dir_index()
        log.info("linked dir index job started")
        return True

    def _loop(self) -> None:
        for ext_root in linked_dir_paths():
            self._prints[str(ext_root.resolve())] = dir_fingerprint(ext_root)
        while not self._stop.wait(poll_seconds()):
            try:
                self._scan_once()
            except Exception:
                log.exception("linked dir watcher error")

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        if not linked_dir_paths():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="linked-dir-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def refresh_fingerprints(self) -> None:
        self._prints.clear()
        for ext_root in linked_dir_paths():
            self._prints[str(ext_root.resolve())] = dir_fingerprint(ext_root)
