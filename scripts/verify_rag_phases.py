#!/usr/bin/env python3
"""Automated acceptance for 易知第五期 RAG Phase A–D. Exit 0 = all pass."""

from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FAILURES: list[str] = []


def ok(name: str) -> None:
    print(f"  PASS  {name}")


def fail(name: str, detail: str) -> None:
    print(f"  FAIL  {name}: {detail}")
    FAILURES.append(f"{name}: {detail}")


def check(cond: bool, name: str, detail: str = "") -> None:
    if cond:
        ok(name)
    else:
        fail(name, detail or "assertion failed")


def phase_a_fts_rrf() -> None:
    print("\n=== Phase A: FTS5 + RRF ===")
    check(Path(ROOT / "lib" / "rag_fts.py").is_file(), "rag_fts.py")
    check(Path(ROOT / "scripts" / "migrate_rag_fts5.py").is_file(), "migrate script")
    from lib.config import rag_fts5_enabled, rag_use_rrf
    from lib.rag import _rrf_fuse

    check(rag_fts5_enabled(), "fts5 config default on")
    check(rag_use_rrf(), "rrf config default on")
    fused = _rrf_fuse([["x", "y"], ["y", "z"]], 60)
    check(fused.get("y", 0) > fused.get("x", 0), "rrf fusion")

    import lib.rag as rag_mod
    from lib.rag import _append_chunks, _search_local
    from lib.rag_fts import bm25_scores, ensure_fts_schema, sync_fts_index

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".rag").mkdir()
        os.environ["MYKNOWLEDGE_FTS5"] = "1"
        store: list[dict] = []
        _append_chunks(store, rel_path="notes/a.md", title="测试", content="专有名词 XYZUnique")
        (root / ".rag" / "chunks.json").write_text(json.dumps({"chunks": store}), encoding="utf-8")
        rag_mod._invalidate_cache(root)
        ensure_fts_schema(root)
        sync_fts_index(store, root)
        scores = bm25_scores("XYZUnique", root=root, limit=5)
        check(bool(scores), "bm25 scores")
        hits = _search_local("XYZUnique", 3, root)
        check(len(hits) >= 1, "fts search hits")


def phase_b_context_rerank() -> None:
    print("\n=== Phase B: Contextual + Rerank ===")
    from lib.config import rag_contextual_enabled, rag_coarse_k, rag_rerank_config
    from lib.rag import _context_prefix, _embed_text_for_chunk

    check(rag_contextual_enabled(), "contextual default on")
    check(rag_coarse_k() >= 5, "coarse_k")
    p = _context_prefix("文档标题", "【章节一】\n正文")
    check("文档标题" in p and "章节一" in p, "context_prefix")
    ch = {"context_prefix": p, "text": "正文"}
    check("文档标题" in _embed_text_for_chunk(ch), "embed_text")
    check(importlib.import_module("lib.rag_rerank"), "rag_rerank module")
    cfg = rag_rerank_config()
    check("enabled" in cfg and "url" in cfg, "rerank config shape")


def phase_c_graph() -> None:
    print("\n=== Phase C: Wiki graph expand ===")
    from lib.config import rag_graph_expand_enabled
    from lib.rag_graph import expand_with_links
    from lib.rag import RagChunk

    check(rag_graph_expand_enabled(), "graph expand default on")
    seed = [
        RagChunk("1", "concepts/a.md", "A", "text a", 1.0, "hybrid"),
    ]
    out = expand_with_links(seed, final_k=5)
    check(len(out) >= 1, "expand returns seed")


def phase_d_agent_eval() -> None:
    print("\n=== Phase D: Agent + eval ===")
    check(Path(ROOT / "lib" / "rag_agent.py").is_file(), "rag_agent.py")
    check(Path(ROOT / "scripts" / "eval_rag.py").is_file(), "eval_rag.py")
    check(Path(ROOT / "tests" / "fixtures" / "rag_golden.jsonl").is_file(), "golden fixture")
    from lib.rag_agent import _rewrite_queries, search_enhanced

    variants = _rewrite_queries("请问 易知 是什么？")
    check(len(variants) >= 2, "query rewrite variants")
    hits = search_enhanced("nonexistent-query-xyz", top_k=3)
    check(isinstance(hits, list), "search_enhanced returns list")

    st = importlib.import_module("lib.rag").rag_status()
    check("fts5_enabled" in st, "rag_status fts5_enabled")


def main() -> int:
    print("易知第五期 RAG — Phase A–D 自动验收")
    phase_a_fts_rrf()
    phase_b_context_rerank()
    phase_c_graph()
    phase_d_agent_eval()
    print("\n" + "=" * 40)
    if FAILURES:
        print(f"FAILED: {len(FAILURES)}")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("ALL RAG PHASES PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
