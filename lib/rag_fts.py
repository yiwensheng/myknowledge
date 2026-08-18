"""SQLite FTS5 BM25 keyword index for RAG chunks."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import wiki_root

FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id UNINDEXED,
    rel_path UNINDEXED,
    title,
    content,
    tokenize='trigram'
);
"""


def _rag_dir(root: Path | None = None) -> Path:
    from .rag import _index_path  # noqa: WPS433

    return _index_path(root).parent


def _db_path(root: Path | None = None) -> Path:
    d = _rag_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    return d / "embeddings.db"


def _connect(root: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(root), timeout=60.0)
    conn.execute("PRAGMA busy_timeout=60000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(FTS_DDL)
    conn.commit()
    return conn


def fts5_table_exists(root: Path | None = None) -> bool:
    try:
        conn = _connect(root)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_fts'"
        ).fetchone()
        conn.close()
        return bool(row)
    except sqlite3.Error:
        return False


def fts5_stats(root: Path | None = None) -> dict[str, int | bool]:
    root = root or wiki_root()
    if not fts5_table_exists(root):
        return {"enabled": False, "chunks": 0}
    try:
        conn = _connect(root)
        n = conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
        conn.close()
        return {"enabled": True, "chunks": int(n)}
    except sqlite3.Error:
        return {"enabled": False, "chunks": 0}


def _escape_fts_query(query: str) -> str:
    q = query.strip()
    if not q:
        return ""
    q = q.replace('"', '""')
    return f'"{q}"'


def bm25_scores(
    query: str,
    *,
    root: Path | None = None,
    limit: int = 40,
    allowed_ids: set[str] | None = None,
) -> dict[str, float]:
    """Return chunk_id -> positive relevance (higher is better)."""
    q = _escape_fts_query(query)
    if not q:
        return {}
    root = root or wiki_root()
    if not fts5_enabled(root):
        return {}
    try:
        conn = _connect(root)
        rows = conn.execute(
            """
            SELECT chunk_id, bm25(chunks_fts) AS rank
            FROM chunks_fts
            WHERE chunks_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (q, max(limit, 1) * 3),
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return {}

    out: dict[str, float] = {}
    for cid, rank in rows:
        sid = str(cid)
        if allowed_ids is not None and sid not in allowed_ids:
            continue
        score = max(0.0, -float(rank))
        out[sid] = score
        if len(out) >= limit:
            break
    return out


def sync_fts_index(chunks: list[dict], root: Path | None = None) -> dict[str, int]:
    """Rebuild FTS rows to match chunk store."""
    root = root or wiki_root()
    if not fts5_enabled(root):
        return {"synced": 0, "skipped": True}
    conn = _connect(root)
    try:
        conn.execute("DELETE FROM chunks_fts")
        batch: list[tuple[str, str, str, str]] = []
        for ch in chunks:
            cid = str(ch.get("id") or "")
            text = str(ch.get("text") or "")
            if not cid or not text.strip():
                continue
            title = str(ch.get("title") or "")
            rel = str(ch.get("rel_path") or "")
            content = f"{title}\n{text}" if title else text
            batch.append((cid, rel, title, content))
        for row in batch:
            conn.execute(
                "INSERT INTO chunks_fts(chunk_id, rel_path, title, content) VALUES (?, ?, ?, ?)",
                row,
            )
        conn.commit()
        return {"synced": len(batch)}
    finally:
        conn.close()


def sync_fts_for_rel_path(rel_path: str, page_chunks: list[dict], root: Path | None = None) -> int:
    root = root or wiki_root()
    if not fts5_enabled(root):
        return 0
    conn = _connect(root)
    try:
        conn.execute("DELETE FROM chunks_fts WHERE rel_path = ?", (rel_path,))
        n = 0
        for ch in page_chunks:
            if str(ch.get("rel_path") or "") != rel_path:
                continue
            cid = str(ch.get("id") or "")
            text = str(ch.get("text") or "")
            if not cid or not text.strip():
                continue
            title = str(ch.get("title") or "")
            content = f"{title}\n{text}" if title else text
            conn.execute(
                "INSERT INTO chunks_fts(chunk_id, rel_path, title, content) VALUES (?, ?, ?, ?)",
                (cid, rel_path, title, content),
            )
            n += 1
        conn.commit()
        return n
    finally:
        conn.close()


def fts5_enabled(root: Path | None = None) -> bool:
    from .config import rag_fts5_enabled

    if not rag_fts5_enabled():
        return False
    return fts5_table_exists(root)


def ensure_fts_schema(root: Path | None = None) -> bool:
    """Create FTS table if enabled; return whether FTS is active."""
    root = root or wiki_root()
    from .config import rag_fts5_enabled

    if not rag_fts5_enabled():
        return False
    _connect(root).close()
    return fts5_table_exists(root)
