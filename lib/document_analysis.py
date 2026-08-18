"""LLM document analysis at ingest time — Cursor-like structured extraction."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from .config import load_dotenv, llm_config

ANALYSIS_HEADING = "## 分析提炼"


@dataclass
class DocumentAnalysis:
    summary: str = ""
    key_points: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    suggested_tags: list[str] = field(default_factory=list)
    wiki_type: str = "source"
    outline: list[str] = field(default_factory=list)
    method: str = "skip"  # llm | excerpt | skip


def ingest_analyze_enabled() -> bool:
    load_dotenv()
    raw = os.environ.get("MYKNOWLEDGE_INGEST_ANALYZE", "").strip().lower()
    if raw in ("0", "false", "no"):
        return False
    if raw in ("1", "true", "yes"):
        return True
    return bool(llm_config().get("api_key"))


def ingest_analyze_max_chars() -> int:
    load_dotenv()
    try:
        return max(2000, min(40_000, int(os.environ.get("MYKNOWLEDGE_INGEST_ANALYZE_MAX_CHARS", "14000"))))
    except ValueError:
        return 14_000


def excerpt_fallback(text: str, max_len: int = 400) -> DocumentAnalysis:
    lines: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("来源:"):
            continue
        lines.append(line)
        if len(" ".join(lines)) > max_len:
            break
    body = " ".join(lines)
    if len(body) > max_len:
        body = body[:max_len] + "…"
    return DocumentAnalysis(summary=body or "（无摘要）", method="excerpt")


def _parse_llm_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        text = m.group(0)
    data = json.loads(text)
    return data if isinstance(data, dict) else {}


def _normalize_list(val: Any, limit: int = 12) -> list[str]:
    if not val:
        return []
    if isinstance(val, str):
        items = re.split(r"[;；\n]", val)
    elif isinstance(val, list):
        items = [str(x) for x in val]
    else:
        return []
    out: list[str] = []
    for item in items:
        s = str(item).strip().strip("-•* ")
        if s and s not in out:
            out.append(s)
        if len(out) >= limit:
            break
    return out


def analyze_document(
    text: str,
    *,
    title: str = "",
    source_kind: str = "document",
    source_url: str = "",
) -> DocumentAnalysis:
    """Extract structured summary from document body for wiki + RAG."""
    body = text.strip()
    if not body:
        return DocumentAnalysis(method="skip")

    if not ingest_analyze_enabled():
        return excerpt_fallback(body)

    cfg = llm_config()
    if not cfg.get("api_key"):
        return excerpt_fallback(body)

    max_chars = ingest_analyze_max_chars()
    sample = body[:max_chars]
    if len(body) > max_chars:
        sample += "\n\n（正文已截断，分析基于前段内容）"

    from .llm import _chat

    meta = f"标题：{title or '（无）'}\n来源类型：{source_kind}"
    if source_url:
        meta += f"\nURL：{source_url}"

    from .config import contrarian_enabled

    want_assumptions = contrarian_enabled()
    assumption_field = (
        "assumptions(文中隐含或明示的核心假设，0-5条，无则空数组), "
        if want_assumptions
        else ""
    )
    system = (
        "你是文档分析助手，任务类似 IDE 助手阅读文件后的精准提炼。"
        "只输出一个 JSON 对象，不要 markdown 代码围栏，不要其它说明。"
        "字段：summary(一句话摘要), key_points(3-8条核心要点), topics(主题词), "
        "entities(人名/机构/产品/术语), facts(可引用的具体事实，含数字/名称), "
        f"{assumption_field}"
        "suggested_tags(入库标签，2-6个), wiki_type(source|concept|entity|comparison|note), "
        "outline(结构大纲，3-8条)。"
        "所有内容必须来自正文，禁止编造；信息不足时对应数组留空、summary 写「正文信息有限」。"
    )
    user = f"{meta}\n\n正文：\n{sample}"

    try:
        raw = _chat(system, user, kind="produce")
        data = _parse_llm_json(raw)
        wiki_type = str(data.get("wiki_type") or "source").strip().lower()
        if wiki_type not in ("source", "concept", "entity", "comparison", "note"):
            wiki_type = "source"
        analysis = DocumentAnalysis(
            summary=str(data.get("summary") or "").strip(),
            key_points=_normalize_list(data.get("key_points")),
            topics=_normalize_list(data.get("topics"), 8),
            entities=_normalize_list(data.get("entities"), 10),
            facts=_normalize_list(data.get("facts"), 10),
            assumptions=_normalize_list(data.get("assumptions"), 5) if want_assumptions else [],
            suggested_tags=_normalize_list(data.get("suggested_tags"), 8),
            wiki_type=wiki_type,
            outline=_normalize_list(data.get("outline"), 10),
            method="llm",
        )
        if not analysis.summary and not analysis.key_points:
            return excerpt_fallback(body)
        return analysis
    except Exception:
        return excerpt_fallback(body)


def format_analysis_markdown(analysis: DocumentAnalysis) -> str:
    if analysis.method == "skip":
        return ""
    lines = [
        ANALYSIS_HEADING,
        "",
        "> 入库时基于正文生成，问答与产出时优先引用本节。",
        "",
    ]
    if analysis.summary:
        lines.extend(["### 一句话摘要", "", analysis.summary, ""])
    if analysis.key_points:
        lines.extend(["### 核心要点", ""])
        lines.extend(f"- {p}" for p in analysis.key_points)
        lines.append("")
    if analysis.assumptions:
        lines.extend(["### 核心假设", ""])
        lines.extend(f"- {a}" for a in analysis.assumptions)
        lines.append("")
    topics = analysis.topics + analysis.entities
    if topics:
        lines.extend(["### 主题与实体", ""])
        lines.extend(f"- {t}" for t in topics[:14])
        lines.append("")
    if analysis.facts:
        lines.extend(["### 可引用事实", ""])
        lines.extend(f"- {f}" for f in analysis.facts)
        lines.append("")
    if analysis.outline:
        lines.extend(["### 结构大纲", ""])
        for i, item in enumerate(analysis.outline, 1):
            lines.append(f"{i}. {item}")
        lines.append("")
    if analysis.method == "excerpt":
        lines.append("*（未调用 LLM，使用前段截断作为摘要）*")
        lines.append("")
    return "\n".join(lines)


def build_source_wiki_body(
    *,
    title: str,
    source_lines: list[str],
    raw_content: str,
    analysis: DocumentAnalysis | None = None,
    body_heading: str = "## 正文",
) -> str:
    parts = [f"# {title}", "", "## 来源", ""]
    parts.extend(source_lines)
    parts.append("")
    if analysis and (analysis.summary or analysis.key_points or analysis.method != "skip"):
        parts.append(format_analysis_markdown(analysis))
    parts.extend([body_heading, "", raw_content, ""])
    return "\n".join(parts)


def merge_tags(existing: list[str], analysis: DocumentAnalysis | None) -> list[str]:
    out = [t.strip() for t in existing if t.strip()]
    if not analysis:
        return out
    for tag in analysis.suggested_tags:
        if tag and tag not in out:
            out.append(tag)
    return out[:12]


def is_analysis_chunk(text: str) -> bool:
    return ANALYSIS_HEADING in text or "### 核心要点" in text or "### 可引用事实" in text
