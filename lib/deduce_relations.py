"""LLM-inferred relations for deduce (推演) graph."""

from __future__ import annotations

import json
import re
from typing import Any

from .deduce_graph import merge_inferred_edges
from .llm import _chat
from .prompts import system_for_deduce
from .rag import RagChunk, format_context


def parse_relations_json(raw: str) -> list[dict[str, Any]]:
    text = (raw or "").strip()
    if not text:
        return []
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return []
    edges = obj.get("edges") if isinstance(obj, dict) else None
    if not isinstance(edges, list):
        return []
    return [e for e in edges if isinstance(e, dict)]


def _build_relations_prompt(query: str, chunks: list[RagChunk], nodes: list[dict]) -> str:
    ctx = format_context(chunks) if chunks else "（无检索片段）"
    node_lines = "\n".join(
        f"- id: {n.get('id')} | title: {n.get('title')}" for n in nodes[:24]
    )
    max_edges = min(16, max(2, len(nodes) * 2))
    return (
        f"推演问题：{query}\n\n"
        f"图谱节点（source/target 须用下列 id 或 title 之一，精确匹配）：\n{node_lines}\n\n"
        f"检索片段（关系须有原文依据，禁止编造）：\n{ctx}\n\n"
        "请深度分析材料中与推演问题相关的**有向关系**，输出 ONLY 一个 JSON 对象（不要 markdown、不要解释）：\n"
        '{"edges":[{"source":"节点id或title","target":"...","label":"关系类型（如：负责/涉及/导致/从属/参与/时序前后）","strength":"强|中|弱"}]}\n\n'
        "要求：\n"
        "1. 每条边须能在检索片段中找到依据；无依据则不输出\n"
        "2. 优先连接 seed 节点与推演主题核心实体，体现因果、组织、时序、参与、依赖等结构\n"
        "3. 箭头方向：source → target 表示「source 对 target 的关系」或「影响/指向 target」\n"
        f"4. 最多 {max_edges} 条；若无可靠关系则 edges 为空数组\n"
    )


def enrich_graph_with_inferred_relations(
    query: str,
    chunks: list[RagChunk],
    graph: dict,
) -> dict:
    nodes = graph.get("nodes") or []
    if len(nodes) < 2:
        return graph
    if not chunks:
        return graph

    prompt = _build_relations_prompt(query, chunks, nodes)
    raw = _chat(system_for_deduce(), prompt, kind="produce")
    inferred = parse_relations_json(raw)
    return merge_inferred_edges(graph, inferred)
