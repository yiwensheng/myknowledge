"""Session memory, Q&A log, and auto-archive for evolving knowledge."""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

from .config import load_dotenv, wiki_root
from .html_answer import html_to_plain
from .wiki import save_page, slugify, today_beijing

MEMORY_DIR_NAME = ".memory"
QA_LOG = "qa-log.jsonl"
SESSIONS_DIR = "sessions"
QA_NOTES_DIR = "notes/qa"


def _env_bool(name: str, default: bool) -> bool:
    load_dotenv()
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def remember_enabled(explicit: bool | None = None) -> bool:
    if explicit is not None:
        return explicit
    return _env_bool("MYKNOWLEDGE_ASK_REMEMBER", True)


def auto_archive_enabled(explicit: bool | None = None) -> bool:
    if explicit is not None:
        return explicit
    return _env_bool("MYKNOWLEDGE_AUTO_ARCHIVE_QA", True)


def max_session_turns() -> int:
    """Max Q&A rounds injected into LLM context (0 = inject entire session)."""
    load_dotenv()
    try:
        return max(0, int(os.environ.get("MYKNOWLEDGE_MEMORY_TURNS", "6")))
    except ValueError:
        return 6


def max_related_qa() -> int:
    load_dotenv()
    try:
        return max(0, int(os.environ.get("MYKNOWLEDGE_MEMORY_QA", "3")))
    except ValueError:
        return 3


def memory_root(root: Path | None = None) -> Path:
    root = root or wiki_root()
    d = root / MEMORY_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    (d / SESSIONS_DIR).mkdir(exist_ok=True)
    return d


def new_session_id() -> str:
    return uuid.uuid4().hex[:16]


def _session_path(session_id: str, root: Path | None = None) -> Path:
    sid = re.sub(r"[^a-zA-Z0-9_-]", "", session_id)[:32]
    return memory_root(root) / SESSIONS_DIR / f"{sid or 'default'}.json"


def load_session(session_id: str, root: Path | None = None) -> dict:
    try:
        _ensure_db(root)
        from . import memory_db

        data = memory_db.load_session(session_id, root=root)
        if data.get("turns"):
            return data
    except OSError:
        pass
    path = _session_path(session_id, root)
    if not path.is_file():
        return {"id": session_id, "turns": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("turns"), list):
            return data
    except json.JSONDecodeError:
        pass
    return {"id": session_id, "turns": []}


def session_messages(session_id: str, root: Path | None = None) -> list[dict[str, str]]:
    """Recent user/assistant turns for multi-turn ask (plain text), plus optional summary."""
    data = load_session(session_id, root)
    turns = data.get("turns") or []
    summary = str(data.get("summary") or "").strip()
    limit = max_session_turns() * 2
    if limit > 0:
        turns = turns[-limit:]
    out: list[dict[str, str]] = []
    if summary:
        out.append(
            {
                "role": "user",
                "content": (
                    "【会话摘要】（压缩自更早对话，非知识库事实；作答仍须依据检索片段）\n"
                    + summary[:2000]
                ),
            }
        )
        out.append(
            {
                "role": "assistant",
                "content": "已了解此前对话要点，将结合摘要与最近轮次继续作答；事实仍只依据检索片段。",
            }
        )
    for t in turns:
        role = str(t.get("role") or "")
        content = str(t.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content[:1200]})
    return out


def _ensure_db(root: Path | None = None) -> None:
    from . import memory_db

    memory_db.ensure_db(root)


def append_session_turn(
    session_id: str,
    role: str,
    content: str,
    root: Path | None = None,
) -> None:
    if not session_id or not content.strip():
        return
    root = root or wiki_root()
    plain = html_to_plain(content)[:2000]
    from datetime import datetime, timedelta, timezone

    beijing = timezone(timedelta(hours=8))
    updated = datetime.now(beijing).strftime("%Y-%m-%d %H:%M")
    data = load_session(session_id, root)
    turns = list(data.get("turns") or [])
    turns.append({"role": role, "content": plain})
    data["id"] = session_id
    data["updated"] = updated
    data["turns"] = turns
    _session_path(session_id, root).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        _ensure_db(root)
        from . import memory_db

        memory_db.insert_turn(session_id, role, plain, root=root)
    except OSError:
        pass


def _qa_log_path(root: Path | None = None) -> Path:
    return memory_root(root) / QA_LOG


def log_qa(
    question: str,
    answer_plain: str,
    sources: list[dict],
    grounded: bool,
    session_id: str = "",
    wiki_page: str = "",
    root: Path | None = None,
) -> None:
    entry = {
        "question": question.strip(),
        "answer": answer_plain[:3000],
        "grounded": grounded,
        "sources": sources,
        "session_id": session_id,
        "wiki_page": wiki_page,
        "at": today_beijing(),
    }
    path = _qa_log_path(root)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    try:
        _ensure_db(root)
        from . import memory_db

        memory_db.insert_qa_entry(entry, root=root)
    except OSError:
        pass


def search_related_qa(question: str, limit: int | None = None, root: Path | None = None) -> list[dict]:
    """Find past grounded Q&A related to current question (token overlap)."""
    limit = limit if limit is not None else max_related_qa()
    if limit <= 0:
        return []
    try:
        _ensure_db(root)
        from . import memory_db

        return memory_db.search_related_qa(question, limit, _tokenize, root=root)
    except OSError:
        pass
    path = _qa_log_path(root)
    if not path.is_file():
        return []
    q_tokens = set(_tokenize(question))
    if not q_tokens:
        return []
    scored: list[tuple[float, dict]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines[-500:]:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not entry.get("grounded"):
            continue
        hay = f"{entry.get('question', '')} {entry.get('answer', '')}"
        t = set(_tokenize(hay))
        overlap = len(q_tokens & t)
        if overlap > 0:
            scored.append((overlap, entry))
    scored.sort(key=lambda x: -x[0])
    return [e for _, e in scored[:limit]]


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    return [m.group() for m in re.finditer(r"[\u4e00-\u9fff]+|[a-zA-Z0-9_]+", text)]


def format_related_qa_block(entries: list[dict]) -> str:
    if not entries:
        return ""
    parts = ["【历史相关问答】（仅供理解上下文与延续话题；作答事实仍须来自下方检索片段）"]
    for i, e in enumerate(entries, 1):
        qid = e.get("id")
        q = e.get("question") or ""
        a = (e.get("answer") or "")[:400]
        prefix = f"{i}. [#{qid}] " if qid is not None else f"{i}. "
        parts.append(f"{prefix}问：{q}\n   答：{a}")
    return "\n".join(parts)


def archive_qa_to_wiki(
    question: str,
    answer_html: str,
    sources: list[dict],
    root: Path | None = None,
) -> str | None:
    """Save grounded Q&A into notes/qa/ and return rel_path."""
    root = root or wiki_root()
    plain = html_to_plain(answer_html)
    if not plain or len(plain) < 20:
        return None
    title = f"问答-{question[:36].strip() or '未命名'}"
    src_lines = []
    for s in sources:
        src_lines.append(f"- {s.get('title') or ''} (`{s.get('path') or ''}`)")
    body = (
        f"# {title}\n\n"
        f"## 问题\n\n{question.strip()}\n\n"
        f"## 回答（归档自提问）\n\n{plain}\n\n"
        f"## 依据来源\n\n"
        + ("\n".join(src_lines) if src_lines else "- （无）\n")
        + f"\n\n> 自动生成于 {today_beijing()}，标签 `qa-archive`\n"
    )
    qa_dir = root / "notes" / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(title)[:60] or "qa"
    rel_path = f"notes/qa/{slug}.md"
    counter = 1
    while (root / rel_path).exists():
        rel_path = f"notes/qa/{slug}-{counter}.md"
        counter += 1
    page = save_page(
        page_type="note",
        title=title,
        body=body,
        tags=["qa-archive", "auto"],
        status="draft",
        rel_path=rel_path,
        root=root,
    )
    return page.rel_path


def get_session_detail(session_id: str, root: Path | None = None) -> dict:
    try:
        _ensure_db(root)
        from . import memory_db

        detail = memory_db.get_session_detail(session_id, root=root)
        if detail.get("turns") or not _session_path(session_id, root).is_file():
            return detail
    except OSError:
        pass
    data = load_session(session_id, root)
    turns = data.get("turns") or []
    preview = ""
    for t in turns:
        if t.get("role") == "user":
            preview = str(t.get("content") or "")[:80]
            break
    return {
        "id": data.get("id") or session_id,
        "updated": data.get("updated") or "",
        "turns": turns,
        "turn_count": len(turns),
        "preview": preview,
    }


def list_sessions(root: Path | None = None) -> list[dict]:
    try:
        _ensure_db(root)
        from . import memory_db

        rows = memory_db.list_sessions(root=root)
        if rows:
            return rows
    except OSError:
        pass
    root = root or wiki_root()
    out: list[dict] = []
    sdir = memory_root(root) / SESSIONS_DIR
    if not sdir.is_dir():
        return out
    paths = sorted(sdir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        turns = data.get("turns") or []
        preview = ""
        for t in turns:
            if t.get("role") == "user":
                preview = str(t.get("content") or "")[:80]
                break
        out.append(
            {
                "id": data.get("id") or path.stem,
                "updated": data.get("updated") or "",
                "turn_count": len(turns),
                "preview": preview,
            }
        )
    return out


def list_qa_history(
    limit: int = 100,
    session_id: str = "",
    offset: int = 0,
    root: Path | None = None,
) -> dict:
    try:
        _ensure_db(root)
        from . import memory_db

        return memory_db.list_qa_history(limit, session_id, offset, root=root)
    except OSError:
        pass
    path = _qa_log_path(root)
    entries: list[dict] = []
    if path.is_file():
        try:
            lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        except OSError:
            lines = []
        for i, line in enumerate(lines):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            entry["_index"] = i
            entries.append(entry)
    if session_id:
        entries = [e for e in entries if e.get("session_id") == session_id]
    entries.reverse()
    total = len(entries)
    slice_ = entries[offset : offset + limit]
    for j, e in enumerate(slice_):
        e["id"] = offset + j
    return {"total": total, "offset": offset, "limit": limit, "entries": slice_}


def get_qa_entry(qa_id: int, root: Path | None = None) -> dict | None:
    try:
        _ensure_db(root)
        from . import memory_db

        return memory_db.get_qa_entry(qa_id, root=root)
    except OSError:
        return None


def update_qa_entry_question(qa_id: int, question: str, root: Path | None = None) -> bool:
    try:
        _ensure_db(root)
        from . import memory_db

        return memory_db.update_qa_question(qa_id, question, root=root)
    except OSError:
        return False


def delete_qa_entry(qa_id: int, root: Path | None = None) -> bool:
    try:
        _ensure_db(root)
        from . import memory_db

        return memory_db.delete_qa_entry(qa_id, root=root)
    except OSError:
        return False


def memory_stats(root: Path | None = None) -> dict:
    root = root or wiki_root()
    try:
        _ensure_db(root)
        from . import memory_db

        return memory_db.memory_stats(root=root)
    except OSError:
        pass
    mroot = memory_root(root)
    sessions = list((mroot / SESSIONS_DIR).glob("*.json"))
    qa_lines = 0
    log_path = _qa_log_path(root)
    if log_path.is_file():
        qa_lines = sum(1 for _ in log_path.open(encoding="utf-8"))
    qa_notes = list((root / "notes" / "qa").rglob("*.md")) if (root / "notes" / "qa").is_dir() else []
    return {
        "storage": "files",
        "sessions": len(sessions),
        "qa_log_entries": qa_lines,
        "qa_archived_notes": len(qa_notes),
    }


def _purpose_excerpt(root: Path | None = None, max_len: int = 240) -> str:
    root = root or wiki_root()
    path = root / "purpose.md"
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    body = " ".join(lines) if lines else text
    return body[:max_len]


def build_evolution_snapshot(*, refresh: bool = True, root: Path | None = None) -> dict:
    """Aggregate evolution stats; optionally persist to .memory/evolution.json."""
    from datetime import datetime, timedelta, timezone

    root = root or wiki_root()
    _ensure_db(root)
    from . import memory_db
    from .output_rules import list_rules

    beijing = timezone(timedelta(hours=8))
    now = datetime.now(beijing)
    week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    stats = memory_db.memory_stats(root=root)
    rules = list_rules(migrate=True)
    enabled = sum(1 for r in rules if r.get("enabled", True))
    latest = memory_db.latest_session(root=root)
    week_delta = {
        "rules_added": memory_db.audit_count_since("rule_create", week_ago, root=root),
        "qa_added": memory_db.qa_count_since(week_ago, root=root),
        "archived_added": 0,
    }
    # archived notes mtime within 7 days
    qa_dir = root / "notes" / "qa"
    if qa_dir.is_dir():
        cutoff = now.timestamp() - 7 * 86400
        week_delta["archived_added"] = sum(
            1 for p in qa_dir.rglob("*.md") if p.stat().st_mtime >= cutoff
        )

    snap = {
        "updated_at": now.strftime("%Y-%m-%d %H:%M"),
        "rules_enabled": enabled,
        "rules_total": len(rules),
        "qa_log_entries": stats.get("qa_log_entries", 0),
        "qa_archived_notes": stats.get("qa_archived_notes", 0),
        "sessions": stats.get("sessions", 0),
        "purpose_excerpt": _purpose_excerpt(root),
        "last_session_id": (latest or {}).get("id") or "",
        "last_session_title": (latest or {}).get("title")
        or (latest or {}).get("preview")
        or "",
        "last_session_updated": (latest or {}).get("updated") or "",
        "last_session_summary": (latest or {}).get("summary") or "",
        "week_delta": week_delta,
    }
    if refresh:
        path = memory_root(root) / "evolution.json"
        path.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return snap


def get_evolution(*, refresh: bool = False, root: Path | None = None) -> dict:
    root = root or wiki_root()
    path = memory_root(root) / "evolution.json"
    if not refresh and path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return build_evolution_snapshot(refresh=True, root=root)


def get_continuity(root: Path | None = None) -> dict:
    evo = build_evolution_snapshot(refresh=True, root=root)
    return {
        "last_session_id": evo.get("last_session_id") or "",
        "last_session_title": evo.get("last_session_title") or "",
        "last_session_updated": evo.get("last_session_updated") or "",
        "last_session_summary": (evo.get("last_session_summary") or "")[:400],
        "purpose_excerpt": evo.get("purpose_excerpt") or "",
        "rules_enabled": evo.get("rules_enabled", 0),
        "rules_total": evo.get("rules_total", 0),
        "week_delta": evo.get("week_delta") or {},
        "evolution": evo,
    }


def update_session_meta(
    session_id: str,
    *,
    title: str | None = None,
    summary: str | None = None,
    root: Path | None = None,
) -> dict:
    _ensure_db(root)
    from . import memory_db

    detail = memory_db.update_session_meta(
        session_id, title=title, summary=summary, root=root
    )
    if summary is not None:
        memory_db.append_audit(
            "summary_clear" if not (summary or "").strip() else "summary_update",
            "summary",
            session_id,
            root=root,
        )
    return detail


def delete_session(session_id: str, root: Path | None = None) -> bool:
    _ensure_db(root)
    from . import memory_db

    ok = memory_db.delete_session(session_id, root=root)
    path = _session_path(session_id, root)
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            pass
    return ok


def maybe_summarize_session(session_id: str, root: Path | None = None) -> str | None:
    """If turns exceed memory window, compress older turns into session.summary."""
    if not session_id:
        return None
    data = load_session(session_id, root)
    turns = data.get("turns") or []
    max_pairs = max_session_turns()
    if max_pairs <= 0:
        return data.get("summary") or None
    keep = max_pairs * 2
    if len(turns) <= keep + 2:
        return data.get("summary") or None

    older = turns[:-keep]
    lines = []
    for t in older[-24:]:
        role = "问" if t.get("role") == "user" else "答"
        lines.append(f"{role}：{str(t.get('content') or '')[:400]}")
    blob = "\n".join(lines)
    prev = str(data.get("summary") or "").strip()
    prompt = (
        "请将下列对话压缩为不超过 400 字的中文要点摘要，只保留已出现的信息，"
        "不要编造事实，不要写成对用户的建议。\n\n"
    )
    if prev:
        prompt += f"已有摘要（可合并修订）：\n{prev}\n\n"
    prompt += f"更早轮次：\n{blob}"

    try:
        from .llm import _chat
        from .prompts import system_for_ask

        raw = _chat(
            "你是会话摘要助手。只压缩对话内容，不回答用户问题。",
            prompt,
            kind="ask",
        )
        summary = html_to_plain(raw).strip()[:2000]
    except Exception:
        # fallback: truncate join
        summary = (prev + "\n" + blob).strip()[:1500] if prev else blob[:1500]

    if not summary:
        return None
    update_session_meta(session_id, summary=summary, root=root)
    return summary


def list_audit(limit: int = 50, offset: int = 0, root: Path | None = None) -> dict:
    _ensure_db(root)
    from . import memory_db

    return memory_db.list_audit(limit=limit, offset=offset, root=root)
