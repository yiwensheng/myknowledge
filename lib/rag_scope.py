"""Scope RAG retrieval to selected wiki pages / assets."""

from __future__ import annotations

from pathlib import Path

from .assets import list_assets
from .config import wiki_root
from .rag import RagChunk
from .wiki import list_pages


def _norm(path: str) -> str:
    return path.replace("\\", "/").strip().lstrip("/")


def expand_scope_paths(paths: list[str], root: Path | None = None) -> list[str]:
    """Include linked wiki pages and assets for each selected path."""
    root = root or wiki_root()
    raw = [_norm(p) for p in paths if p and str(p).strip()]
    if not raw:
        return []

    out: set[str] = set()
    assets = {a.rel_path: a for a in list_assets(root)}
    pages = {p.rel_path: p for p in list_pages(root, include_inbox=False)}
    wiki_by_asset = {a.wiki_page: a.rel_path for a in assets.values() if a.wiki_page}

    for sp in raw:
        out.add(sp)
        if sp in assets:
            a = assets[sp]
            if a.wiki_page:
                out.add(_norm(a.wiki_page))
        if sp in pages:
            p = pages[sp]
            if p.asset_path:
                out.add(_norm(p.asset_path))
        if sp in wiki_by_asset:
            out.add(_norm(wiki_by_asset[sp]))

    return sorted(out)


def chunk_matches_scope(chunk: RagChunk, scope_paths: list[str]) -> bool:
    if not scope_paths:
        return True
    rel = _norm(chunk.rel_path)
    asset = _norm(chunk.asset_path or "")
    title = (chunk.title or "").strip()
    for sp in scope_paths:
        s = _norm(sp)
        if not s:
            continue
        if rel == s or asset == s:
            return True
        # External linked-dir prefix: @external:D:/docs matches @external:D:/docs/a.pdf
        if s.startswith("@external:") and (rel == s or rel.startswith(s.rstrip("/") + "/")):
            return True
        if rel.endswith("/" + s) or s.endswith("/" + rel):
            return True
        if asset and (asset.endswith("/" + s) or s.endswith("/" + asset)):
            return True
        base = s.split("/")[-1]
        if base and (rel.endswith("/" + base) or asset.endswith("/" + base) or title == base):
            return True
        if rel.startswith(s + "/") or asset.startswith(s + "/"):
            return True
    return False


def filter_index_chunks(
    chunks: list[dict],
    scope_paths: list[str] | None,
    root: Path | None = None,
) -> list[dict]:
    """Keep only index rows belonging to scoped paths (before scoring)."""
    if not scope_paths:
        return chunks
    expanded = expand_scope_paths(scope_paths, root)
    if not expanded:
        return chunks
    out: list[dict] = []
    for ch in chunks:
        rc = RagChunk(
            chunk_id=str(ch.get("id") or ""),
            rel_path=str(ch.get("rel_path") or ""),
            title=str(ch.get("title") or ""),
            text=str(ch.get("text") or ""),
            asset_path=str(ch.get("asset_path") or ""),
        )
        if chunk_matches_scope(rc, expanded):
            out.append(ch)
    return out
