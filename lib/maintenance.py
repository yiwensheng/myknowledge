"""Draft pages and open-questions summary for maintenance UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import wiki_root
from .ingest import defer_wiki_index_update
from .wiki import list_pages, read_page, save_page


def _safe_page_path(rel: str, root: Path) -> Path | None:
    rel = rel.strip().replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        return None
    path = (root / rel).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


def list_draft_summary(*, limit: int = 30) -> dict[str, Any]:
    root = wiki_root()
    drafts = [p for p in list_pages(include_inbox=False) if p.status == "draft"]
    no_links = [p for p in drafts if not p.links]
    items = [
        {
            "rel_path": p.rel_path,
            "title": p.title,
            "type": p.type,
            "links_count": len(p.links or []),
            "tags": p.tags or [],
        }
        for p in sorted(drafts, key=lambda x: x.rel_path)[:limit]
    ]
    oq = root / "index" / "open-questions.md"
    oq_exists = oq.is_file()
    return {
        "draft_total": len(drafts),
        "no_links_total": len(no_links),
        "items": items,
        "open_questions_path": str(oq) if oq_exists else "",
        "note": "草稿需 refined 后检索权重更高；无 links 条目见 open-questions.md",
    }


def mark_pages_refined(paths: list[str], *, root: Path | None = None) -> dict[str, Any]:
    root = root or wiki_root()
    refined: list[str] = []
    skipped: list[str] = []
    errors: list[dict[str, str]] = []
    seen: set[str] = set()
    for rel in paths:
        rel = str(rel or "").strip().replace("\\", "/")
        if not rel or rel in seen:
            continue
        seen.add(rel)
        page_path = _safe_page_path(rel, root)
        if not page_path:
            errors.append({"path": rel, "error": "not found"})
            continue
        try:
            old = read_page(page_path, root)
            if old.status == "refined":
                skipped.append(rel)
                continue
            save_page(
                page_type=old.type,
                title=old.title,
                body=old.body,
                tags=old.tags,
                status="refined",
                links=old.links,
                rel_path=rel,
                root=root,
                asset_path=old.asset_path,
                asset_mime=old.asset_mime,
            )
            refined.append(rel)
        except OSError as exc:
            errors.append({"path": rel, "error": str(exc)})
    if refined:
        defer_wiki_index_update(root)
    return {
        "refined_count": len(refined),
        "refined": refined,
        "skipped_count": len(skipped),
        "skipped": skipped,
        "errors": errors,
    }


def mark_all_drafts_refined(*, limit: int = 0, root: Path | None = None) -> dict[str, Any]:
    root = root or wiki_root()
    drafts = [p for p in list_pages(include_inbox=False, root=root) if p.status == "draft"]
    if limit > 0:
        drafts = drafts[:limit]
    paths = [p.rel_path for p in drafts]
    result = mark_pages_refined(paths, root=root)
    result["requested_total"] = len(paths)
    return result


def list_external_rag_chunks(*, page: int = 1, size: int = 40, q: str = "") -> dict[str, Any]:
    from .paging import paginate
    from .rag import _load_index_lazy

    root = wiki_root()
    chunks, _ = _load_index_lazy(root)
    rows: list[dict[str, Any]] = []
    q_lower = q.strip().lower()
    for ch in chunks:
        rel = str(ch.get("rel_path") or "")
        if not rel.startswith("@external:"):
            continue
        title = str(ch.get("title") or rel)
        if q_lower and q_lower not in title.lower() and q_lower not in rel.lower():
            continue
        rows.append(
            {
                "rel_path": rel,
                "title": title,
                "external_path": rel.removeprefix("@external:").split("/", 1)[0],
                "preview": str(ch.get("text") or "")[:200],
            }
        )
    rows.sort(key=lambda x: x["rel_path"])
    return paginate(rows, page, size, max_size=200)
