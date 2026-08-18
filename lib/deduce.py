"""Deduce (推演): RAG-grounded scenario analysis with wiki subgraph."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from .citation import enrich_source, linkify_fragment_refs
from .config import llm_config, rag_top_k
from .deduce_graph import build_deduce_subgraph
from .deduce_relations import enrich_graph_with_inferred_relations
from .llm import _chat_stream
from .markdown_render import markdown_to_html
from .prompts import (
    DEDUCE_GRAPH_SECTION,
    DEDUCE_REPORT_SECTIONS,
    system_for_deduce,
    title_from_markdown,
)
from .rag import RagChunk, format_context
from .rag_agent import search_enhanced
from .wiki import save_page


def _graph_summary(graph: dict) -> dict:
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": [
            {"id": n.get("id"), "title": n.get("title"), "seed": n.get("seed"), "page_type": n.get("page_type")}
            for n in nodes[:30]
        ],
        "edges": [
            {
                "source": e.get("source"),
                "target": e.get("target"),
                "label": e.get("label"),
                "strength": e.get("strength"),
                "source_type": e.get("source_type"),
            }
            for e in edges[:40]
        ],
    }


def _build_report_prompt(query: str, chunks: list[RagChunk]) -> str:
    ctx = format_context(chunks) if chunks else "（无匹配片段，请在报告中说明库内依据不足，勿编造）"
    owner_hint = ""
    try:
        from .persona_config import load_owner_config, query_refers_to_owner

        if query_refers_to_owner(query, load_owner_config()):
            owner_hint = (
                "\n\n【主人指代】推演问题中的「我/本人/姓名」指知识库主人；"
                "闪念与时间线记录视为其本人随记，须在检索片段中找依据。"
            )
    except Exception:
        pass
    return (
        f"推演问题：{query}{owner_hint}\n\n"
        f"参考检索片段（共 {len(chunks)} 段，须充分引用）：\n{ctx}\n\n"
        f"请撰写推演报告，严格按以下 Markdown 结构（不要 YAML frontmatter）：\n{DEDUCE_REPORT_SECTIONS}"
    )


def _build_graph_prompt(query: str, graph: dict, report_excerpt: str) -> str:
    summary = _graph_summary(graph)
    return (
        f"推演问题：{query}\n\n"
        f"关系子图摘要（JSON）：\n{json.dumps(summary, ensure_ascii=False, indent=2)}\n\n"
        f"已撰写的推演报告（节选）：\n{report_excerpt[:1200]}\n\n"
        f"请撰写关系图解读，严格按以下结构：\n{DEDUCE_GRAPH_SECTION}"
    )


def _note_title(query: str) -> str:
    q = query.strip().replace("\n", " ")
    if len(q) > 48:
        q = q[:48].rstrip() + "…"
    return f"推演：{q}" if q else "推演"


def _finalize_deduce(
    query: str,
    report_md: str,
    graph_md: str,
    chunks: list[RagChunk],
    graph: dict,
) -> dict[str, Any]:
    report_md = (report_md or "").strip()
    graph_md = (graph_md or "").strip()
    body_parts = [p for p in [report_md, graph_md] if p]
    body = "\n\n---\n\n".join(body_parts) if body_parts else "（未生成正文）"
    title = title_from_markdown(body, _note_title(query))
    if not body.lstrip().startswith("#"):
        body = f"# {title}\n\n{body}"

    sources = [
        enrich_source(
            index=i,
            title=c.title,
            rel_path=c.rel_path,
            score=c.score,
            retrieval=c.retrieval,
            text=c.text,
            asset_path=c.asset_path,
        )
        for i, c in enumerate(chunks, 1)
    ]
    content_html = linkify_fragment_refs(markdown_to_html(body), sources)
    link_titles = [str(n.get("title") or "") for n in (graph.get("nodes") or []) if n.get("title")]

    result: dict[str, Any] = {
        "query": query,
        "title": title,
        "content": body,
        "content_html": content_html,
        "sources": sources,
        "graph": graph,
        "rag_chunks_used": len(chunks),
        "model": llm_config().get("model"),
    }

    page = save_page(
        page_type="note",
        title=title,
        body=body,
        tags=["推演"],
        status="draft",
        links=link_titles[:12],
        extra_meta={"deduce": True},
    )
    from .ingest import defer_refresh_rag

    defer_refresh_rag()
    result["wiki_page"] = page.rel_path
    return result


def deduce_stream(
    query: str,
    *,
    top_k: int | None = None,
    scope_paths: list[str] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield SSE events: status | graph | token | done | error."""
    q = (query or "").strip()
    if not q:
        yield {"type": "error", "message": "请输入推演问题"}
        return

    yield {"type": "status", "text": "正在检索知识库…"}
    k = top_k if top_k is not None else rag_top_k("produce")
    k = max(k, rag_top_k("produce"))
    chunks = search_enhanced(q, top_k=k, scope_paths=scope_paths)
    graph = build_deduce_subgraph(chunks)
    yield {"type": "status", "text": "正在分析实体关系（大模型）…"}
    graph = enrich_graph_with_inferred_relations(q, chunks, graph)
    yield {"type": "graph", "graph": graph}
    yield {"type": "status", "text": f"已找到 {len(chunks)} 段素材，正在撰写推演报告…"}

    system = system_for_deduce()
    report_parts: list[str] = []
    for token in _chat_stream(system, _build_report_prompt(q, chunks), kind="produce"):
        report_parts.append(token)
        yield {"type": "token", "text": token, "section": "report"}

    report_md = "".join(report_parts)
    yield {"type": "status", "text": "正在撰写关系图解读…"}

    graph_parts: list[str] = []
    for token in _chat_stream(system, _build_graph_prompt(q, graph, report_md), kind="produce"):
        graph_parts.append(token)
        yield {"type": "token", "text": token, "section": "graph_commentary"}

    graph_md = "".join(graph_parts)
    result = _finalize_deduce(q, report_md, graph_md, chunks, graph)
    yield {"type": "done", **result}
