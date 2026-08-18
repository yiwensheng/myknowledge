"""Tests for deduce subgraph builder."""

from __future__ import annotations

from pathlib import Path

from lib.deduce_graph import build_deduce_subgraph, merge_inferred_edges
from lib.deduce_relations import parse_relations_json
from lib.rag import RagChunk
from lib.wiki import serialize_page


def _write_page(root: Path, rel: str, title: str, links: list[str] | None = None) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "title": title,
        "type": "concept" if rel.startswith("concepts/") else "note",
        "tags": [],
        "created": "2026-01-01",
        "updated": "2026-01-01",
        "status": "refined",
        "links": links or [],
    }
    path.write_text(serialize_page(meta, f"# {title}\n\nbody"), encoding="utf-8")


def test_build_subgraph_from_seeds(tmp_path: Path) -> None:
    _write_page(tmp_path, "concepts/a.md", "A", links=["B"])
    _write_page(tmp_path, "concepts/b.md", "B", links=[])

    chunks = [
        RagChunk(
            chunk_id="1",
            rel_path="concepts/a.md",
            title="A",
            text="alpha",
            score=1.0,
            retrieval="local",
        )
    ]
    g = build_deduce_subgraph(chunks, root=tmp_path, max_nodes=20)
    ids = {n["id"] for n in g["nodes"]}
    assert "concepts/a.md" in ids
    assert "concepts/b.md" in ids
    assert any(e["source"] == "concepts/a.md" and e["target"] == "concepts/b.md" for e in g["edges"])
    seed = next(n for n in g["nodes"] if n["id"] == "concepts/a.md")
    assert seed["seed"] is True


def test_empty_chunks_returns_empty_graph(tmp_path: Path) -> None:
    g = build_deduce_subgraph([], root=tmp_path)
    assert g == {"nodes": [], "edges": []}


def test_merge_inferred_edges_by_title() -> None:
    graph = {
        "nodes": [
            {"id": "a.md", "title": "司建新", "seed": True},
            {"id": "b.md", "title": "纠纷事实", "seed": True},
        ],
        "edges": [],
    }
    inferred = [
        {"source": "司建新", "target": "纠纷事实", "label": "涉及", "strength": "强"},
    ]
    out = merge_inferred_edges(graph, inferred)
    assert len(out["edges"]) == 1
    e = out["edges"][0]
    assert e["source"] == "a.md"
    assert e["target"] == "b.md"
    assert e["label"] == "涉及"
    assert e["source_type"] == "inferred"
    assert e["directed"] is True


def test_parse_relations_json_fence() -> None:
    raw = '```json\n{"edges":[{"source":"A","target":"B","label":"负责"}]}\n```'
    edges = parse_relations_json(raw)
    assert len(edges) == 1
    assert edges[0]["label"] == "负责"
