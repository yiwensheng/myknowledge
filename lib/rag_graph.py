"""Lightweight wiki-link graph expansion for RAG retrieval."""

from __future__ import annotations

from pathlib import Path

from .config import rag_graph_expand_enabled, rag_graph_max_hops, wiki_root
from .rag import RagChunk, _load_index
from .wiki import list_pages, read_page


def _norm(path: str) -> str:
    return path.replace("\\", "/").strip().lstrip("/")


def _resolve_link(target: str, pages_by_path: dict[str, object], pages_by_title: dict[str, object]) -> str | None:
    t = (target or "").strip()
    if not t:
        return None
    n = _norm(t)
    if n in pages_by_path:
        return n
    if not n.endswith(".md"):
        cand = f"{n}.md" if "/" in n else None
        if cand and cand in pages_by_path:
            return cand
    for d in ("concepts", "entities", "sources", "comparisons", "notes", "archive"):
        cand = f"{d}/{n}" if not n.endswith(".md") else n
        if cand in pages_by_path:
            return cand
        cand2 = f"{d}/{n}.md"
        if cand2 in pages_by_path:
            return cand2
    low = t.lower()
    if low in pages_by_title:
        return pages_by_title[low]
    return None


def _page_type_boost(page_type: str) -> float:
    if page_type in ("entity", "concept"):
        return 1.1
    if page_type == "source":
        return 1.05
    return 1.0


def expand_with_links(
    chunks: list[RagChunk],
    *,
    root: Path | None = None,
    final_k: int | None = None,
    max_hops: int | None = None,
) -> list[RagChunk]:
    if not chunks or not rag_graph_expand_enabled():
        return chunks

    root = root or wiki_root()
    hops = rag_graph_max_hops() if max_hops is None else max_hops
    if hops <= 0:
        return chunks

    pages = list_pages(root, include_inbox=False)
    pages_by_path = {p.rel_path: p for p in pages}
    pages_by_title = {p.title.lower(): p.rel_path for p in pages if p.title}

    store, _ = _load_index(root)
    by_path: dict[str, list[dict]] = {}
    for ch in store:
        rel = str(ch.get("rel_path") or "")
        by_path.setdefault(rel, []).append(ch)

    seen_ids = {c.chunk_id for c in chunks}
    out = list(chunks)
    per_page = 2
    max_expand = max(4, (final_k or len(chunks)) * 2)

    frontier: list[tuple[str, float, int]] = []
    for c in chunks:
        rel = _norm(c.rel_path.split("#")[0])
        frontier.append((rel, c.score, 0))

    while frontier and len(out) < len(chunks) + max_expand:
        rel, base_score, hop = frontier.pop(0)
        if hop >= hops:
            continue
        page = pages_by_path.get(rel)
        if not page:
            try:
                page = read_page(root / rel, root)
            except OSError:
                continue
        links = getattr(page, "links", None) or []
        decay = 0.85 ** (hop + 1)
        boost = _page_type_boost(getattr(page, "type", "note"))
        for link in links:
            target = _resolve_link(str(link), pages_by_path, pages_by_title)
            if not target:
                continue
            added = 0
            for ch in by_path.get(target, [])[:per_page]:
                cid = str(ch.get("id"))
                if cid in seen_ids:
                    continue
                seen_ids.add(cid)
                score = base_score * decay * boost
                out.append(
                    RagChunk(
                        chunk_id=cid,
                        rel_path=str(ch.get("rel_path") or target),
                        title=str(ch.get("title") or ""),
                        text=str(ch.get("text") or ""),
                        score=score,
                        retrieval=f"graph-hop{hop + 1}",
                        asset_path=str(ch.get("asset_path") or ""),
                        tags=[str(t) for t in (ch.get("tags") or [])],
                    )
                )
                added += 1
                if len(out) >= len(chunks) + max_expand:
                    break
            if added and hop + 1 < hops:
                frontier.append((target, base_score * decay, hop + 1))

    out.sort(key=lambda x: -x.score)
    if final_k:
        return out[:final_k]
    return out
