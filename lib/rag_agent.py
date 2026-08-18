"""Constrained multi-round RAG retrieval with audit log."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import (
    rag_agent_enabled,
    rag_agent_score_threshold,
    rag_hyde_enabled,
    wiki_root,
)
from .rag import RagChunk, search as rag_search

BEIJING = timezone(timedelta(hours=8))
_LOG = "rag_agent.jsonl"


def _log_path(root: Path | None = None) -> Path:
    root = root or wiki_root()
    d = root / ".memory"
    d.mkdir(parents=True, exist_ok=True)
    return d / _LOG


def _rewrite_queries(question: str) -> list[str]:
    q = question.strip()
    if not q:
        return []
    variants = [q]
    stripped = re.sub(r"[？?。！!；;，,、\s]+", " ", q).strip()
    if stripped and stripped not in variants:
        variants.append(stripped)
    no_q = re.sub(r"^(请问|请|什么是|是什么|如何|怎么|为什么|为何)\s*", "", stripped, flags=re.I)
    if no_q and no_q not in variants:
        variants.append(no_q)
    keywords = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_]{3,}", q)
    if len(keywords) >= 2:
        kw = " ".join(keywords[:8])
        if kw not in variants:
            variants.append(kw)
    try:
        from .persona_config import expand_queries_for_owner, load_owner_config

        for extra in expand_queries_for_owner(q, load_owner_config()):
            if extra not in variants:
                variants.append(extra)
    except Exception:
        pass
    return variants[:6]


def _hyde_passage(question: str) -> str:
    """Hypothetical document embedding (HyDE): short passage that might answer the question."""
    q = question.strip()
    if not q:
        return ""
    try:
        from .llm import _chat

        raw = _chat(
            "根据用户问题写一段 80～180 字的假想知识库笔记片段，像真实笔记口吻，"
            "只写可能相关的事实性表述，不要问答格式，不要说「假设」「我猜测」。",
            q,
            kind="ask",
        )
        text = (raw or "").strip()
        text = re.sub(r"^```[\s\S]*?```$", "", text).strip()
        return text[:500] if text else ""
    except Exception:
        return ""


def _needs_agent(chunks: list[RagChunk]) -> bool:
    if not chunks:
        return True
    return max(c.score for c in chunks) < rag_agent_score_threshold()


def _append_log(entry: dict, root: Path | None = None) -> None:
    p = _log_path(root)
    line = json.dumps(entry, ensure_ascii=False)
    with p.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _merge_best(a: list[RagChunk], b: list[RagChunk], top_k: int | None) -> list[RagChunk]:
    by_id: dict[str, RagChunk] = {}
    for c in a + b:
        prev = by_id.get(c.chunk_id)
        if not prev or c.score > prev.score:
            by_id[c.chunk_id] = c
    merged = sorted(by_id.values(), key=lambda x: -x.score)
    if top_k is not None:
        return merged[:top_k]
    return merged


def search_enhanced(
    query: str,
    *,
    top_k: int | None = None,
    root: Path | None = None,
    scope_paths: list[str] | None = None,
) -> list[RagChunk]:
    """RAG search with optional constrained agent rounds and optional HyDE."""
    root = root or wiki_root()
    rounds: list[dict] = []
    best: list[RagChunk] = []

    queries = [query.strip()]
    if rag_agent_enabled() and not scope_paths:
        queries = _rewrite_queries(query) or queries
    else:
        try:
            from .persona_config import expand_queries_for_owner, load_owner_config, query_refers_to_owner

            owner = load_owner_config()
            if query_refers_to_owner(query.strip(), owner):
                for extra in expand_queries_for_owner(query.strip(), owner):
                    if extra not in queries:
                        queries.append(extra)
        except Exception:
            pass

    if rag_hyde_enabled() and not scope_paths:
        hypo = _hyde_passage(query)
        if hypo and hypo not in queries:
            queries.append(hypo)

    query_list = queries[:6]
    max_rounds = len(query_list)

    for i, q in enumerate(query_list):
        hits = rag_search(q, top_k=top_k, root=root, scope_paths=scope_paths)
        rounds.append(
            {
                "round": i + 1,
                "query": q[:120],
                "hits": len(hits),
                "top_score": hits[0].score if hits else 0,
            }
        )
        best = _merge_best(best, hits, top_k)
        if hits and rag_agent_enabled() and not _needs_agent(hits) and not rag_hyde_enabled():
            break
        if i >= max_rounds - 1:
            break

    if (rag_agent_enabled() or rag_hyde_enabled()) and len(queries) > 1:
        _append_log(
            {
                "ts": datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M:%S"),
                "question": query,
                "hyde": rag_hyde_enabled(),
                "rounds": rounds,
                "selected": len(best),
            },
            root,
        )
    return best
