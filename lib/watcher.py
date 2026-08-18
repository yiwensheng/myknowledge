"""Filesystem watcher: auto ingest + RAG for all supported media."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from .config import WATCH_DIRS, wiki_root
from .ingest import ingest_file
from .media_types import is_supported

log = logging.getLogger("myknowledge.watcher")

POLL_SECONDS = 3.0


class WikiWatcher:
    def __init__(self, root: Path | None = None, poll: float = POLL_SECONDS) -> None:
        self.root = root or wiki_root()
        self.poll = poll
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._seen: dict[str, float] = {}
        self._bootstrapped = False

    def _should_watch(self, path: Path) -> bool:
        if not path.is_file():
            return False
        if "inbox-processed" in path.parts or ".extracted" in path.parts:
            return False
        if path.name == "manifest.json":
            return False
        if path.suffix.lower() == ".json" and ".rag" in path.parts:
            return False
        return is_supported(path.suffix)

    def _scan_once(self) -> list[str]:
        processed: list[str] = []
        pending_sync = False

        for dir_name in WATCH_DIRS:
            base = self.root / dir_name
            if not base.is_dir():
                continue
            for path in base.rglob("*"):
                if not self._should_watch(path):
                    continue
                key = str(path.resolve())
                mtime = path.stat().st_mtime
                prev = self._seen.get(key)

                if not self._bootstrapped:
                    self._seen[key] = mtime
                    continue

                if prev is not None and prev >= mtime:
                    continue
                self._seen[key] = mtime

                rel: str | None = None
                if dir_name == "inbox":
                    rel = ingest_file(path, self.root, defer_index=True)
                elif dir_name == "assets":
                    from .assets import find_by_hash, file_sha256

                    digest = file_sha256(path)
                    if find_by_hash(digest, self.root):
                        rel = str(path.relative_to(self.root))
                        pending_sync = True
                    else:
                        rel = ingest_file(path, self.root, move_inbox=False, defer_index=True)
                else:
                    rel = str(path.relative_to(self.root))
                    pending_sync = True

                if rel:
                    processed.append(rel)
                    log.info("watcher processed: %s", rel)

        if pending_sync or any(processed):
            from .index_writer import schedule_debounced_sync

            schedule_debounced_sync(self.root)

        self._bootstrapped = True
        return processed

    def run_once(self) -> list[str]:
        return self._scan_once()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._scan_once()
            except Exception as e:
                log.warning("watcher error: %s", e)
            self._stop.wait(self.poll)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="WikiWatcher")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.poll + 1)
