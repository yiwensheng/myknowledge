"""Library views: original assets and RAG knowledge entries."""

from __future__ import annotations

from pathlib import Path

from .assets import list_assets
from .config import wiki_root
from .paging import paginate
from .rag import _load_index
from .wiki import list_pages


def _match_query(text: str, q: str) -> bool:
    if not q:
        return True
    return q.lower() in text.lower()


def list_rag_library(
    page: int = 1,
    size: int = 20,
    q: str = "",
    root: Path | None = None,
) -> dict:
    root = root or wiki_root()
    chunks, _ = _load_index(root)
    page_map = {p.rel_path: p for p in list_pages(root, include_inbox=False)}
    asset_by_path = {a.rel_path: a for a in list_assets(root)}
    asset_by_wiki = {a.wiki_page: a for a in list_assets(root) if a.wiki_page}

    items: list[dict] = []
    for ch in chunks:
        rel = str(ch.get("rel_path") or "")
        wp = page_map.get(rel)
        asset_path = str(ch.get("asset_path") or "")
        if not asset_path and wp:
            asset_path = wp.asset_path
        if not asset_path:
            asset = asset_by_wiki.get(rel)
            if asset:
                asset_path = asset.rel_path

        tags = ch.get("tags") or []
        if not tags and wp:
            tags = wp.tags
        tag_list = [str(t) for t in tags] if isinstance(tags, list) else []

        asset_rec = asset_by_path.get(asset_path)
        asset_filename = asset_rec.filename if asset_rec else ""

        title = str(ch.get("title") or "")
        text = str(ch.get("text") or "")
        haystack = " ".join([title, text, rel, asset_path, asset_filename, " ".join(tag_list)])
        if not _match_query(haystack, q.strip()):
            continue

        items.append(
            {
                "id": str(ch.get("id") or ""),
                "title": title,
                "text": text,
                "rel_path": rel,
                "wiki_page": rel if wp else "",
                "asset_path": asset_path,
                "asset_filename": asset_filename,
                "tags": tag_list,
            }
        )

    return paginate(items, page, size)
