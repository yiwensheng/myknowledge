"""Build wiki-link subgraph for deduce (推演) visualization."""

from __future__ import annotations

from pathlib import Path

from .config import wiki_root
from .rag import RagChunk
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


def build_deduce_subgraph(
    chunks: list[RagChunk],
    *,
    root: Path | None = None,
    max_nodes: int = 24,
    max_hops: int = 1,
) -> dict:
    """Return {nodes: [...], edges: [...]} for force-directed graph UI."""
    root = root or wiki_root()
    if not chunks:
        return {"nodes": [], "edges": []}

    seed_scores: dict[str, float] = {}
    for c in chunks:
        rel = _norm(c.rel_path.split("#")[0])
        seed_scores[rel] = max(seed_scores.get(rel, 0.0), float(c.score or 0.0))

    pages = list_pages(root, include_inbox=False)
    pages_by_path = {p.rel_path: p for p in pages}
    pages_by_title = {p.title.lower(): p.rel_path for p in pages if p.title}

    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    edge_set: set[tuple[str, str]] = set()

    def _add_node(rel: str, *, seed: bool, score: float) -> None:
        if rel in nodes or len(nodes) >= max_nodes:
            return
        page = pages_by_path.get(rel)
        if not page:
            try:
                page = read_page(root / rel, root)
            except OSError:
                page = None
        nodes[rel] = {
            "id": rel,
            "title": page.title if page else rel.split("/")[-1].replace(".md", ""),
            "page_type": page.type if page else "note",
            "seed": seed,
            "score": round(score, 3),
        }

    for rel, score in sorted(seed_scores.items(), key=lambda x: -x[1]):
        _add_node(rel, seed=True, score=score)

    frontier: list[tuple[str, float, int]] = [(rel, seed_scores[rel], 0) for rel in seed_scores]
    while frontier and len(nodes) < max_nodes:
        rel, base_score, hop = frontier.pop(0)
        if hop >= max_hops:
            continue
        page = pages_by_path.get(rel)
        if not page:
            try:
                page = read_page(root / rel, root)
            except OSError:
                continue
        for link in page.links or []:
            target = _resolve_link(str(link), pages_by_path, pages_by_title)
            if not target:
                continue
            key = (rel, target)
            if key not in edge_set:
                edge_set.add(key)
                edges.append(
                    {
                        "source": rel,
                        "target": target,
                        "label": str(link),
                        "directed": True,
                        "source_type": "wiki",
                        "strength": "中",
                    }
                )
            decay = base_score * (0.85 ** (hop + 1))
            if target not in nodes:
                _add_node(target, seed=False, score=decay)
            if target in nodes and hop + 1 < max_hops:
                frontier.append((target, decay, hop + 1))

    return {"nodes": list(nodes.values()), "edges": edges}


def _resolve_node_ref(ref: str, nodes: list[dict]) -> str | None:
    t = (ref or "").strip()
    if not t:
        return None
    by_id = {n["id"]: n["id"] for n in nodes}
    if t in by_id:
        return t
    n = _norm(t)
    if n in by_id:
        return n
    by_title = {str(n.get("title") or "").lower(): n["id"] for n in nodes if n.get("title")}
    low = t.lower()
    if low in by_title:
        return by_title[low]
    for title, nid in by_title.items():
        if not title:
            continue
        if low in title or title in low:
            return nid
    stem = t.split("/")[-1].replace(".md", "").lower()
    for title, nid in by_title.items():
        if stem and (stem in title or title.endswith(stem)):
            return nid
    return None


def merge_inferred_edges(graph: dict, inferred: list[dict]) -> dict:
    """Merge LLM-inferred directed edges into subgraph."""
    nodes = graph.get("nodes") or []
    edges = list(graph.get("edges") or [])
    if not nodes or not inferred:
        return graph

    edge_set = {(e.get("source"), e.get("target")) for e in edges if e.get("source") and e.get("target")}
    for item in inferred:
        if not isinstance(item, dict):
            continue
        src = _resolve_node_ref(str(item.get("source") or ""), nodes)
        tgt = _resolve_node_ref(str(item.get("target") or ""), nodes)
        if not src or not tgt or src == tgt:
            continue
        key = (src, tgt)
        if key in edge_set:
            continue
        edge_set.add(key)
        strength = str(item.get("strength") or "中").strip()
        if strength not in ("强", "中", "弱"):
            strength = "中"
        edges.append(
            {
                "source": src,
                "target": tgt,
                "label": str(item.get("label") or "").strip(),
                "directed": True,
                "source_type": "inferred",
                "strength": strength,
            }
        )

    return {"nodes": nodes, "edges": edges}
