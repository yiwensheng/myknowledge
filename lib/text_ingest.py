"""Ingest pasted plain text into wiki + RAG."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .config import wiki_root
from .document_analysis import analyze_document, build_source_wiki_body, merge_tags
from .ingest import defer_wiki_index_update
from .rag import upsert_page_index
from .wiki import save_page, slugify, today_beijing


def _first_line_title(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^#+\s*", "", line)
        return line[:80]
    return "粘贴文本"


def ingest_text(text: str, title: str | None = None, root: Path | None = None) -> dict:
    """Save pasted text under assets/, create sources/ page, rebuild RAG."""
    body = text.strip()
    if len(body) < 10:
        raise ValueError("文本太短，请至少输入 10 个字符")

    root = root or wiki_root()
    page_title = (title or "").strip() or _first_line_title(body)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]

    texts_dir = root / "assets" / "documents" / "texts"
    texts_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(page_title)[:60] or digest
    local_name = f"{digest}-{slug}.md"
    local_path = texts_dir / local_name
    local_path.write_text(body, encoding="utf-8")
    local_rel = local_path.relative_to(root).as_posix()

    analysis = analyze_document(body, title=page_title, source_kind="paste")
    source_lines = [
        "- 导入方式: 粘贴文本",
        f"- 本地化文件: `{local_rel}`",
        f"- 存档日期: {today_beijing()}",
    ]
    wiki_body = build_source_wiki_body(
        title=page_title,
        source_lines=source_lines,
        raw_content=body,
        analysis=analysis,
    )

    wiki_page = save_page(
        page_type=analysis.wiki_type if analysis.method == "llm" else "source",
        title=page_title,
        body=wiki_body,
        tags=merge_tags(["text-import", "paste"], analysis),
        status="draft",
        asset_path=local_rel,
        asset_mime="text/markdown",
        root=root,
    )
    chunks = upsert_page_index(wiki_page, root, embed_async=True)
    defer_wiki_index_update(root)

    return {
        "title": page_title,
        "wiki_page": wiki_page.rel_path,
        "localized": local_rel,
        "chars": len(body),
        "rag_chunks": chunks,
        "analysis_method": analysis.method,
    }
