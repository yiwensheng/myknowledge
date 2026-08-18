"""Local vector embeddings (OpenAI-compatible API) stored in SQLite."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import ssl
import struct
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from .config import rag_embedding_config, wiki_root

EMBED_DB = "embeddings.db"
BATCH_SIZE = 32
_CONNECT_TIMEOUT = 60.0
_query_cache: dict[str, list[float]] = {}
_QUERY_CACHE_MAX = 64


def _rag_dir(root: Path | None = None) -> Path:
    from .rag import _index_path  # noqa: WPS433

    return _index_path(root).parent


def _db_path(root: Path | None = None) -> Path:
    d = _rag_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    return d / EMBED_DB


def _connect(root: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(root), timeout=_CONNECT_TIMEOUT)
    conn.execute("PRAGMA busy_timeout=60000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS embeddings (
            chunk_id TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            text_hash TEXT NOT NULL,
            dim INTEGER NOT NULL,
            vector BLOB NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _exec_retry(conn: sqlite3.Connection, sql: str, params: tuple, *, retries: int = 8) -> None:
    for attempt in range(retries):
        try:
            conn.execute(sql, params)
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt >= retries - 1:
                raise
            time.sleep(0.25 * (attempt + 1))


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack(blob: bytes, dim: int) -> list[float]:
    return list(struct.unpack(f"{dim}f", blob))


def _embed_url(base: str) -> str:
    base = base.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/embeddings"
    return f"{base}/v1/embeddings"


def _post_embeddings(texts: list[str], cfg: dict[str, str]) -> list[list[float]]:
    if not texts:
        return []
    body = json.dumps({"model": cfg["model"], "input": texts}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        _embed_url(cfg["api_base"]),
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['api_key']}",
        },
        method="POST",
    )
    ctx = ssl.create_default_context()
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            items = sorted(data.get("data") or [], key=lambda x: x.get("index", 0))
            return [list(item.get("embedding") or []) for item in items]
        except Exception as exc:
            last_err = exc
            if attempt < 2:
                time.sleep(1.0 + attempt)
                continue
            raise last_err from exc
    raise RuntimeError("embedding request failed")


def embeddings_available() -> bool:
    cfg = rag_embedding_config()
    return bool(cfg.get("enabled") and cfg.get("api_key"))


_embed_retry_lock = threading.Lock()
_embed_retry_scheduled: set[str] = set()


def _schedule_embed_retry(root: Path | None = None) -> None:
    root = root or wiki_root()
    key = str(root.resolve())
    with _embed_retry_lock:
        if key in _embed_retry_scheduled:
            return
        _embed_retry_scheduled.add(key)

    def _run() -> None:
        try:
            from .rag import _load_index_lazy

            chunks, _ = _load_index_lazy(root)
            sync_embeddings(chunks, root)
        finally:
            with _embed_retry_lock:
                _embed_retry_scheduled.discard(key)

    threading.Timer(45.0, _run).start()


def sync_embeddings(chunks: list[dict], root: Path | None = None) -> dict[str, int | str]:
    """Embed new/changed chunks; remove orphans. Returns stats."""
    cfg = rag_embedding_config()
    if not cfg.get("enabled"):
        return {"enabled": False, "embedded": 0, "skipped": len(chunks)}
    if not cfg.get("api_key"):
        return {"enabled": True, "error": "missing_api_key", "embedded": 0}

    model = str(cfg["model"])
    conn = _connect(root)
    existing = {
        row[0]: (row[1], row[2])
        for row in conn.execute(
            "SELECT chunk_id, text_hash, model FROM embeddings WHERE model = ?",
            (model,),
        )
    }
    live_ids = {str(ch["id"]) for ch in chunks}
    removed = 0
    for cid in list(existing.keys()):
        if cid not in live_ids:
            _exec_retry(conn, "DELETE FROM embeddings WHERE chunk_id = ?", (cid,))
            removed += 1

    todo: list[tuple[str, str]] = []
    for ch in chunks:
        cid = str(ch["id"])
        text = str(ch.get("text") or "")
        if not text.strip():
            continue
        th = _text_hash(text)
        embed_src = str(ch.get("context_prefix") or "").strip()
        embed_input = f"{embed_src}\n{text}" if embed_src else text
        th_embed = _text_hash(embed_input)
        if existing.get(cid) == (th_embed, model):
            continue
        todo.append((cid, embed_input))

    embedded = 0
    errors = 0
    for i in range(0, len(todo), BATCH_SIZE):
        batch = todo[i : i + BATCH_SIZE]
        try:
            vectors = _post_embeddings([t for _, t in batch], cfg)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            conn.commit()
            conn.close()
            pending = len(todo) - embedded
            if pending > 0:
                _schedule_embed_retry(root)
            return {
                "enabled": True,
                "embedded": embedded,
                "removed": removed,
                "pending": pending,
                "error": str(exc),
            }
        for (cid, text), vec in zip(batch, vectors, strict=False):
            if not vec:
                errors += 1
                continue
            th = _text_hash(text)
            _exec_retry(
                conn,
                """
                INSERT INTO embeddings(chunk_id, model, text_hash, dim, vector)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    model=excluded.model,
                    text_hash=excluded.text_hash,
                    dim=excluded.dim,
                    vector=excluded.vector
                """,
                (cid, model, th, len(vec), _pack(vec)),
            )
            embedded += 1
        conn.commit()
    conn.close()
    result = {
        "enabled": True,
        "embedded": embedded,
        "removed": removed,
        "errors": errors,
        "model": model,
    }
    pending = len(todo) - embedded
    if pending > 0:
        result["pending"] = pending
        _schedule_embed_retry(root)
    return result


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)


def embed_query(query: str, root: Path | None = None) -> list[float] | None:
    cfg = rag_embedding_config()
    if not cfg.get("enabled") or not cfg.get("api_key"):
        return None
    model = str(cfg.get("model") or "")
    cache_key = f"{model}:{hashlib.sha256(query.encode('utf-8')).hexdigest()[:16]}"
    if cache_key in _query_cache:
        return _query_cache[cache_key]
    try:
        vecs = _post_embeddings([query], cfg)
        vec = vecs[0] if vecs else None
        if vec:
            if len(_query_cache) >= _QUERY_CACHE_MAX:
                _query_cache.pop(next(iter(_query_cache)))
            _query_cache[cache_key] = vec
        return vec
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def vector_scores(
    query_vec: list[float],
    chunk_ids: list[str],
    root: Path | None = None,
) -> dict[str, float]:
    if not query_vec or not chunk_ids:
        return {}
    cfg = rag_embedding_config()
    model = str(cfg.get("model") or "")
    conn = _connect(root)
    placeholders = ",".join("?" * len(chunk_ids))
    rows = conn.execute(
        f"SELECT chunk_id, dim, vector FROM embeddings WHERE model = ? AND chunk_id IN ({placeholders})",
        [model, *chunk_ids],
    ).fetchall()
    conn.close()
    out: dict[str, float] = {}
    for cid, dim, blob in rows:
        vec = _unpack(blob, int(dim))
        out[str(cid)] = _cosine(query_vec, vec)
    return out


def embedding_stats(root: Path | None = None) -> dict[str, int | str | bool]:
    cfg = rag_embedding_config()
    root = root or wiki_root()
    if not _db_path(root).is_file():
        return {"enabled": bool(cfg.get("enabled")), "count": 0, "model": cfg.get("model", ""), "completeness_pct": 0}
    conn = _connect(root)
    model = str(cfg.get("model") or "")
    count = conn.execute(
        "SELECT COUNT(*) FROM embeddings WHERE model = ?",
        (model,),
    ).fetchone()[0]
    conn.close()
    expected = 0
    try:
        from .rag import _load_index_lazy

        chunks, _ = _load_index_lazy(root)
        expected = sum(1 for ch in chunks if str(ch.get("text") or "").strip())
    except Exception:
        expected = int(count)
    completeness = int(round(100 * count / expected)) if expected else 100
    return {
        "enabled": bool(cfg.get("enabled")),
        "count": int(count),
        "model": model,
        "expected": expected,
        "completeness_pct": min(100, completeness),
    }
