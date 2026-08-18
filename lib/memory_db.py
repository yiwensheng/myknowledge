"""SQLite index for session turns and Q&A log (.memory/memory.db)."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import wiki_root

MEMORY_DIR_NAME = ".memory"
MEMORY_DB = "memory.db"
QA_LOG = "qa-log.jsonl"
SESSIONS_DIR = "sessions"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT '',
  preview TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS turns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  at TEXT NOT NULL DEFAULT '',
  FOREIGN KEY (session_id) REFERENCES sessions(id)
);
CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, id);
CREATE TABLE IF NOT EXISTS qa_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  grounded INTEGER NOT NULL DEFAULT 0,
  sources TEXT NOT NULL DEFAULT '[]',
  session_id TEXT NOT NULL DEFAULT '',
  wiki_page TEXT NOT NULL DEFAULT '',
  at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_qa_session ON qa_log(session_id, id DESC);
CREATE TABLE IF NOT EXISTS memory_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT NOT NULL DEFAULT '',
  action TEXT NOT NULL DEFAULT '',
  object_type TEXT NOT NULL DEFAULT '',
  object_id TEXT NOT NULL DEFAULT '',
  detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_at ON memory_audit(at DESC);
"""


def memory_root(root: Path | None = None) -> Path:
    root = root or wiki_root()
    d = root / MEMORY_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    (d / SESSIONS_DIR).mkdir(exist_ok=True)
    return d


def qa_log_path(root: Path | None = None) -> Path:
    return memory_root(root) / QA_LOG


def db_path(root: Path | None = None) -> Path:
    return memory_root(root) / MEMORY_DB


def beijing_now() -> str:
    beijing = timezone(timedelta(hours=8))
    return datetime.now(beijing).strftime("%Y-%m-%d %H:%M")


@contextmanager
def _connect(root: Path | None = None):
    path = db_path(root)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def ensure_schema(root: Path | None = None) -> None:
    with _connect(root) as conn:
        conn.executescript(_SCHEMA)
        for col, decl in (
            ("summary", "TEXT NOT NULL DEFAULT ''"),
            ("summary_updated_at", "TEXT NOT NULL DEFAULT ''"),
            ("title", "TEXT NOT NULL DEFAULT ''"),
        ):
            if not _column_exists(conn, "sessions", col):
                conn.execute(f"ALTER TABLE sessions ADD COLUMN {col} {decl}")


def append_audit(
    action: str,
    object_type: str,
    object_id: str,
    detail: str = "",
    root: Path | None = None,
) -> None:
    ensure_schema(root)
    with _connect(root) as conn:
        conn.execute(
            """
            INSERT INTO memory_audit (at, action, object_type, object_id, detail)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                beijing_now(),
                (action or "")[:80],
                (object_type or "")[:40],
                (object_id or "")[:120],
                (detail or "")[:500],
            ),
        )


def list_audit(limit: int = 50, offset: int = 0, root: Path | None = None) -> dict:
    ensure_schema(root)
    limit = max(1, min(200, limit))
    offset = max(0, offset)
    with _connect(root) as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM memory_audit").fetchone()["n"]
        rows = conn.execute(
            """
            SELECT id, at, action, object_type, object_id, detail
            FROM memory_audit
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    return {
        "total": total,
        "items": [
            {
                "id": r["id"],
                "at": r["at"],
                "action": r["action"],
                "object_type": r["object_type"],
                "object_id": r["object_id"],
                "detail": r["detail"],
            }
            for r in rows
        ],
    }


def _session_preview(turns: list[dict]) -> str:
    for t in turns:
        if t.get("role") == "user":
            return str(t.get("content") or "")[:80]
    return ""


def migrate_from_files(root: Path | None = None) -> dict:
    """Import legacy session JSON + qa-log.jsonl into SQLite (idempotent)."""
    root = root or wiki_root()
    ensure_schema(root)
    stats = {"sessions": 0, "turns": 0, "qa_entries": 0}

    sdir = memory_root(root) / SESSIONS_DIR
    if sdir.is_dir():
        for path in sorted(sdir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            sid = str(data.get("id") or path.stem)
            turns = data.get("turns") or []
            if not isinstance(turns, list):
                continue
            updated = str(data.get("updated") or "")
            preview = _session_preview(turns)
            with _connect(root) as conn:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM turns WHERE session_id = ?",
                    (sid,),
                ).fetchone()
                if row and row["n"] >= len(turns):
                    continue
                conn.execute("DELETE FROM turns WHERE session_id = ?", (sid,))
                conn.execute(
                    """
                    INSERT INTO sessions (id, created_at, updated_at, preview)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                      updated_at = excluded.updated_at,
                      preview = excluded.preview
                    """,
                    (sid, updated, updated, preview),
                )
                for t in turns:
                    role = str(t.get("role") or "")
                    content = str(t.get("content") or "")
                    if role not in ("user", "assistant") or not content.strip():
                        continue
                    conn.execute(
                        "INSERT INTO turns (session_id, role, content, at) VALUES (?, ?, ?, ?)",
                        (sid, role, content, updated),
                    )
                    stats["turns"] += 1
                stats["sessions"] += 1

    log_path = qa_log_path(root)
    if log_path.is_file():
        try:
            lines = [ln.strip() for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        except OSError:
            lines = []
        with _connect(root) as conn:
            db_count = conn.execute("SELECT COUNT(*) AS n FROM qa_log").fetchone()["n"]
        for line in lines[db_count:]:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            insert_qa_entry(entry, root=root)
            stats["qa_entries"] += 1

    return stats


def ensure_db(root: Path | None = None) -> None:
    root = root or wiki_root()
    ensure_schema(root)
    migrate_from_files(root)


def insert_turn(
    session_id: str,
    role: str,
    content: str,
    root: Path | None = None,
) -> None:
    at = beijing_now()
    preview = content[:80] if role == "user" else ""
    with _connect(root) as conn:
        conn.execute(
            """
            INSERT INTO sessions (id, created_at, updated_at, preview)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              updated_at = excluded.updated_at,
              preview = CASE
                WHEN ? != '' THEN ?
                ELSE sessions.preview
              END
            """,
            (session_id, at, at, preview, preview, preview),
        )
        conn.execute(
            "INSERT INTO turns (session_id, role, content, at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, at),
        )


def insert_qa_entry(entry: dict, root: Path | None = None) -> None:
    sources = entry.get("sources") or []
    with _connect(root) as conn:
        conn.execute(
            """
            INSERT INTO qa_log (question, answer, grounded, sources, session_id, wiki_page, at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(entry.get("question") or ""),
                str(entry.get("answer") or "")[:3000],
                1 if entry.get("grounded") else 0,
                json.dumps(sources, ensure_ascii=False),
                str(entry.get("session_id") or ""),
                str(entry.get("wiki_page") or ""),
                str(entry.get("at") or beijing_now()),
            ),
        )


def load_session(session_id: str, root: Path | None = None) -> dict:
    ensure_schema(root)
    with _connect(root) as conn:
        rows = conn.execute(
            "SELECT role, content FROM turns WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        meta = conn.execute(
            "SELECT id, updated_at, summary, summary_updated_at, title, preview FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    turns = [{"role": r["role"], "content": r["content"]} for r in rows]
    return {
        "id": session_id,
        "updated": meta["updated_at"] if meta else "",
        "summary": meta["summary"] if meta else "",
        "summary_updated_at": meta["summary_updated_at"] if meta else "",
        "title": meta["title"] if meta else "",
        "preview": meta["preview"] if meta else "",
        "turns": turns,
    }


def get_session_detail(session_id: str, root: Path | None = None) -> dict:
    data = load_session(session_id, root)
    turns = data.get("turns") or []
    preview = data.get("preview") or _session_preview(turns)
    title = (data.get("title") or "").strip() or preview
    return {
        "id": session_id,
        "updated": data.get("updated") or "",
        "turns": turns,
        "turn_count": len(turns),
        "preview": preview,
        "title": title,
        "summary": data.get("summary") or "",
        "summary_updated_at": data.get("summary_updated_at") or "",
    }


def update_session_meta(
    session_id: str,
    *,
    title: str | None = None,
    summary: str | None = None,
    root: Path | None = None,
) -> dict:
    ensure_schema(root)
    sid = (session_id or "").strip()
    if not sid:
        raise ValueError("session_id required")
    with _connect(root) as conn:
        row = conn.execute("SELECT id FROM sessions WHERE id = ?", (sid,)).fetchone()
        if not row:
            raise ValueError("会话不存在")
        if title is not None:
            conn.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                (title.strip()[:120], beijing_now(), sid),
            )
        if summary is not None:
            conn.execute(
                """
                UPDATE sessions
                SET summary = ?, summary_updated_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (summary.strip()[:4000], beijing_now(), beijing_now(), sid),
            )
    return get_session_detail(sid, root=root)


def delete_session(session_id: str, root: Path | None = None) -> bool:
    ensure_schema(root)
    sid = (session_id or "").strip()
    if not sid:
        return False
    with _connect(root) as conn:
        existed = conn.execute("SELECT 1 FROM sessions WHERE id = ?", (sid,)).fetchone()
        conn.execute("DELETE FROM turns WHERE session_id = ?", (sid,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
    if not existed:
        return False
    append_audit("session_delete", "session", sid, root=root)
    return True


def list_sessions(root: Path | None = None) -> list[dict]:
    ensure_schema(root)
    with _connect(root) as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.updated_at, s.preview, s.title, s.summary,
                   (SELECT COUNT(*) FROM turns t WHERE t.session_id = s.id) AS turn_count
            FROM sessions s
            ORDER BY s.updated_at DESC, s.id DESC
            """
        ).fetchall()
    return [
        {
            "id": r["id"],
            "updated": r["updated_at"] or "",
            "turn_count": r["turn_count"] or 0,
            "preview": r["preview"] or "",
            "title": (r["title"] or "").strip() or (r["preview"] or ""),
            "summary": r["summary"] or "",
        }
        for r in rows
    ]


def latest_session(root: Path | None = None) -> dict | None:
    items = list_sessions(root=root)
    return items[0] if items else None


def qa_count_since(since: str, root: Path | None = None) -> int:
    """Count qa_log rows with at >= since (string compare works for YYYY-MM-DD…)."""
    ensure_schema(root)
    with _connect(root) as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM qa_log WHERE at >= ?",
            (since,),
        ).fetchone()["n"]


def audit_count_since(action_prefix: str, since: str, root: Path | None = None) -> int:
    ensure_schema(root)
    with _connect(root) as conn:
        return conn.execute(
            """
            SELECT COUNT(*) AS n FROM memory_audit
            WHERE at >= ? AND action LIKE ?
            """,
            (since, f"{action_prefix}%"),
        ).fetchone()["n"]


def list_qa_history(
    limit: int = 100,
    session_id: str = "",
    offset: int = 0,
    root: Path | None = None,
) -> dict:
    where = ""
    params: list[object] = []
    if session_id:
        where = "WHERE session_id = ?"
        params.append(session_id)
    with _connect(root) as conn:
        total = conn.execute(f"SELECT COUNT(*) AS n FROM qa_log {where}", params).fetchone()["n"]
        rows = conn.execute(
            f"""
            SELECT id, question, answer, grounded, sources, session_id, wiki_page, at
            FROM qa_log
            {where}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
    entries: list[dict] = []
    for r in rows:
        try:
            sources = json.loads(r["sources"] or "[]")
        except json.JSONDecodeError:
            sources = []
        entries.append(
            {
                "id": r["id"],
                "question": r["question"],
                "answer": r["answer"],
                "grounded": bool(r["grounded"]),
                "sources": sources,
                "session_id": r["session_id"],
                "wiki_page": r["wiki_page"],
                "at": r["at"],
            }
        )
    return {"total": total, "offset": offset, "limit": limit, "entries": entries}


def _row_to_qa_entry(r: sqlite3.Row) -> dict:
    try:
        sources = json.loads(r["sources"] or "[]")
    except json.JSONDecodeError:
        sources = []
    return {
        "id": r["id"],
        "question": r["question"],
        "answer": r["answer"],
        "grounded": bool(r["grounded"]),
        "sources": sources,
        "session_id": r["session_id"],
        "wiki_page": r["wiki_page"],
        "at": r["at"],
    }


def get_qa_entry(qa_id: int, root: Path | None = None) -> dict | None:
    with _connect(root) as conn:
        row = conn.execute(
            """
            SELECT id, question, answer, grounded, sources, session_id, wiki_page, at
            FROM qa_log WHERE id = ?
            """,
            (qa_id,),
        ).fetchone()
    return _row_to_qa_entry(row) if row else None


def update_qa_question(qa_id: int, question: str, root: Path | None = None) -> bool:
    q = question.strip()
    if not q:
        return False
    with _connect(root) as conn:
        cur = conn.execute("UPDATE qa_log SET question = ? WHERE id = ?", (q, qa_id))
        return cur.rowcount > 0


def search_related_qa(
    question: str,
    limit: int,
    tokenize,
    root: Path | None = None,
) -> list[dict]:
    if limit <= 0:
        return []
    q_tokens = set(tokenize(question))
    if not q_tokens:
        return []
    with _connect(root) as conn:
        rows = conn.execute(
            """
            SELECT id, question, answer, grounded, sources, session_id, wiki_page, at
            FROM qa_log
            WHERE grounded = 1
            ORDER BY id DESC
            LIMIT 800
            """
        ).fetchall()
    scored: list[tuple[float, dict]] = []
    for r in rows:
        hay = f"{r['question']} {r['answer']}"
        qset = set(tokenize(hay))
        overlap = len(q_tokens & qset)
        if overlap <= 0:
            continue
        # Prefer denser overlap + question-title hits
        q_hit = len(q_tokens & set(tokenize(r["question"] or "")))
        score = float(overlap) + 0.5 * float(q_hit)
        try:
            sources = json.loads(r["sources"] or "[]")
        except json.JSONDecodeError:
            sources = []
        scored.append(
            (
                score,
                {
                    "id": r["id"],
                    "question": r["question"],
                    "answer": r["answer"],
                    "grounded": True,
                    "sources": sources,
                    "session_id": r["session_id"],
                    "wiki_page": r["wiki_page"],
                    "at": r["at"],
                },
            )
        )
    scored.sort(key=lambda x: -x[0])
    return [e for _, e in scored[:limit]]


def memory_stats(root: Path | None = None) -> dict:
    root = root or wiki_root()
    ensure_schema(root)
    with _connect(root) as conn:
        sessions = conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
        turns = conn.execute("SELECT COUNT(*) AS n FROM turns").fetchone()["n"]
        qa_lines = conn.execute("SELECT COUNT(*) AS n FROM qa_log").fetchone()["n"]
    qa_notes = list((root / "notes" / "qa").rglob("*.md")) if (root / "notes" / "qa").is_dir() else []
    return {
        "storage": "sqlite",
        "db_path": str(db_path(root)),
        "sessions": sessions,
        "turns": turns,
        "qa_log_entries": qa_lines,
        "qa_archived_notes": len(qa_notes),
    }


def delete_qa_entry(qa_id: int, root: Path | None = None) -> bool:
    ensure_schema(root)
    with _connect(root) as conn:
        cur = conn.execute("DELETE FROM qa_log WHERE id = ?", (qa_id,))
        ok = cur.rowcount > 0
    if ok:
        append_audit("qa_delete", "qa", str(qa_id), root=root)
    return ok
