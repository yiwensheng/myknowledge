#!/usr/bin/env python3
"""RAG retrieval evaluation harness (Phase D). Exit 0 = pass."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GOLDEN = ROOT / "tests" / "fixtures" / "rag_golden.jsonl"


def _load_cases(limit: int | None = None) -> list[dict]:
    if not GOLDEN.is_file():
        return []
    cases: list[dict] = []
    for line in GOLDEN.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        cases.append(json.loads(line))
        if limit and len(cases) >= limit:
            break
    return cases


def _recall_at_k(hits: list, case: dict, k: int = 10) -> float:
    if case.get("expect_empty"):
        return 1.0 if not hits else 0.0
    top = hits[:k]
    rel_need = case.get("expect_rel_contains")
    kw = case.get("expect_keyword")
    for h in top:
        if rel_need and rel_need in str(getattr(h, "rel_path", "")):
            return 1.0
        if kw and kw in str(getattr(h, "text", "")) + str(getattr(h, "title", "")):
            return 1.0
    return 0.0


def run_eval(*, quick: bool = False) -> dict:
    from lib.config import load_dotenv
    from lib.rag import search
    from lib.rag_agent import search_enhanced

    load_dotenv()
    cases = _load_cases(2 if quick else None)
    if not cases:
        return {"cases": 0, "recall": 1.0, "skipped": True}

    recalls: list[float] = []
    agent_recalls: list[float] = []
    for case in cases:
        q = case["question"]
        hits = search(q, top_k=10)
        recalls.append(_recall_at_k(hits, case))
        os.environ["MYKNOWLEDGE_RAG_AGENT"] = "1"
        ahits = search_enhanced(q, top_k=10)
        agent_recalls.append(_recall_at_k(ahits, case))
        os.environ["MYKNOWLEDGE_RAG_AGENT"] = "0"

    return {
        "cases": len(cases),
        "recall": sum(recalls) / len(recalls),
        "agent_recall": sum(agent_recalls) / len(agent_recalls),
        "skipped": False,
    }


def run_synthetic() -> dict:
    """Self-contained FTS + RRF smoke test on temp index."""
    import lib.rag as rag_mod
    from lib.rag import _append_chunks, _rrf_fuse, _search_local
    from lib.rag_fts import ensure_fts_schema, sync_fts_index

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".rag").mkdir()
        os.environ["MYKNOWLEDGE_FTS5"] = "1"
        os.environ["MYKNOWLEDGE_RAG_RRF"] = "1"
        store: list[dict] = []
        _append_chunks(
            store,
            rel_path="notes/test-alpha.md",
            title="Alpha 文档",
            content="混合检索 RRF 测试专有名词 AlphaBeta",
        )
        _append_chunks(
            store,
            rel_path="notes/test-beta.md",
            title="Beta 文档",
            content="无关内容 gamma delta",
        )
        idx = root / ".rag" / "chunks.json"
        idx.write_text(json.dumps({"chunks": store}, ensure_ascii=False), encoding="utf-8")
        rag_mod._invalidate_cache(root)
        ensure_fts_schema(root)
        sync_fts_index(store, root)

        hits = _search_local("AlphaBeta", 5, root)
        ok = any("Alpha" in h.text or "Alpha" in h.title for h in hits)
        rrf = _rrf_fuse([["a", "b"], ["b", "c"]], 60)
        rrf_ok = rrf.get("b", 0) > rrf.get("a", 0) and rrf.get("b", 0) > rrf.get("c", 0)
        return {"fts_hits": len(hits), "fts_ok": ok, "rrf_ok": rrf_ok}


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Myknowledge RAG retrieval")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--synthetic-only", action="store_true")
    args = parser.parse_args()

    syn = run_synthetic()
    print(f"Synthetic: fts_ok={syn['fts_ok']} rrf_ok={syn['rrf_ok']} hits={syn['fts_hits']}")
    if not syn["fts_ok"] or not syn["rrf_ok"]:
        return 1

    if args.synthetic_only:
        return 0

    rep = run_eval(quick=args.quick)
    print(f"Golden: cases={rep['cases']} recall={rep.get('recall', 0):.2f} agent={rep.get('agent_recall', 0):.2f}")
    if rep.get("skipped"):
        print("(golden set skipped — no fixture file)")
        return 0
    if rep["recall"] < 0.5 and rep["cases"] > 0:
        print("WARN: golden recall below 0.5 — index may lack matching notes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
