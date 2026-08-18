"""Memos-style quick capture: timeline notes in notes/*.md."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .config import wiki_root
from .wiki import WikiPage, read_page, serialize_page

BEIJING = timezone(timedelta(hours=8))
HASHTAG_RE = re.compile(r"(?:^|[\s(（])#([\w\u4e00-\u9fff-]+)")


def extract_hashtags(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for tag in HASHTAG_RE.findall(text):
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def _memo_title(content: str) -> str:
    line = content.strip().split("\n", 1)[0].strip()
    line = re.sub(r"^#+\s*", "", line)
    if len(line) > 80:
        return line[:77] + "…"
    return line or "闪记"


def _memo_slug(root) -> str:
    now = datetime.now(BEIJING)
    base = f"memo-{now.strftime('%Y%m%d-%H%M%S')}"
    if not (root / "notes" / f"{base}.md").exists():
        return base
    for i in range(1, 100):
        candidate = f"{base}-{i}"
        if not (root / "notes" / f"{candidate}.md").exists():
            return candidate
    return f"{base}-{uuid4().hex[:6]}"


def _now_beijing() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M")


def _parse_updated_ts(value: str) -> float:
    value = (value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=BEIJING).timestamp()
        except ValueError:
            continue
    return 0.0


def _is_pinned(page: WikiPage) -> bool:
    return bool(getattr(page, "pinned", False))


def today_beijing_date() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%d")


def _memo_date_key(page: WikiPage) -> str:
    raw = (page.updated or page.created or "").strip()
    if len(raw) >= 10:
        return raw[:10]
    return ""


def _memo_time_key(page: WikiPage) -> str:
    raw = (page.updated or page.created or "").strip()
    if len(raw) >= 16:
        return raw[11:16]
    return ""


def _is_flash_memo(page: WikiPage) -> bool:
    if getattr(page, "memo", False):
        return True
    name = page.path.name.lower()
    return name.startswith("memo-") and name.endswith(".md")


def list_memo_pages(
    root=None,
    tag: str | None = None,
    date: str | None = None,
    flash_only: bool = True,
) -> list[WikiPage]:
    """Notes in notes/ for timeline; optional date + flash-only filter."""
    root = root or wiki_root()
    notes_dir = root / "notes"
    if not notes_dir.is_dir():
        return []
    pages: list[WikiPage] = []
    for path in notes_dir.rglob("*.md"):
        if "inbox-processed" in path.parts:
            continue
        pages.append(read_page(path, root))
    if flash_only:
        pages = [p for p in pages if _is_flash_memo(p)]
    if date:
        date = date.strip()[:10]
        pages = [p for p in pages if _memo_date_key(p) == date]
    if tag:
        tag = tag.strip().lstrip("#")
        pages = [
            p
            for p in pages
            if tag in (p.tags or []) or f"#{tag}" in p.body
        ]
    pages.sort(
        key=lambda p: (_is_pinned(p), _parse_updated_ts(p.updated or p.created)),
        reverse=True,
    )
    return pages


def collect_memo_tags(pages: list[WikiPage]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for p in pages:
        for t in p.tags or []:
            if t and t not in seen:
                seen.add(t)
                out.append(t)
    return out


def memo_to_dict(page: WikiPage) -> dict[str, Any]:
    d = page.to_dict()
    d["body"] = page.body
    d["memo"] = bool(getattr(page, "memo", False))
    d["pinned"] = bool(getattr(page, "pinned", False))
    d["date"] = _memo_date_key(page)
    d["time"] = _memo_time_key(page)
    return d


def create_memo(content: str, root=None, folder_ids: list[str] | None = None) -> WikiPage:
    content = content.strip()
    if not content:
        raise ValueError("内容不能为空")
    root = root or wiki_root()
    tags = extract_hashtags(content)
    slug = _memo_slug(root)
    now = _now_beijing()
    from .folders import normalize_folder_ids

    meta = {
        "title": _memo_title(content),
        "type": "note",
        "tags": tags,
        "created": now,
        "updated": now,
        "status": "draft",
        "memo": True,
        "pinned": False,
        "links": [],
        "folder_ids": normalize_folder_ids(folder_ids, root),
    }
    path = root / "notes" / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_page(meta, content), encoding="utf-8")
    return read_page(path, root)


def update_memo(
    rel_path: str,
    *,
    content: str | None = None,
    pinned: bool | None = None,
    folder_ids: list[str] | None = None,
    root=None,
) -> WikiPage:
    root = root or wiki_root()
    path = root / rel_path
    if not path.is_file():
        raise FileNotFoundError("memo not found")
    meta, body = _read_meta_body(path)
    if content is not None:
        body = content.strip()
        if not body:
            raise ValueError("内容不能为空")
        meta["title"] = _memo_title(body)
        meta["tags"] = extract_hashtags(body)
        meta["memo"] = True
    if pinned is not None:
        meta["pinned"] = bool(pinned)
    if folder_ids is not None:
        from .folders import normalize_folder_ids

        meta["folder_ids"] = normalize_folder_ids(folder_ids, root)
    meta["updated"] = _now_beijing()
    meta["type"] = meta.get("type") or "note"
    path.write_text(serialize_page(meta, body), encoding="utf-8")
    return read_page(path, root)


def _read_meta_body(path) -> tuple[dict, str]:
    from .wiki import parse_frontmatter

    text = path.read_text(encoding="utf-8")
    return parse_frontmatter(text)
