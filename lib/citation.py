"""Citation metadata and HTML links for ask answers."""

from __future__ import annotations

import re

from .html_answer import esc

_PAGE_RE = re.compile(r"---\s*第(\d+)页\s*---|---\s*幻灯片\s*(\d+)\s*---", re.I)


def extract_page_hint(text: str) -> int | None:
    m = _PAGE_RE.search(text or "")
    if not m:
        return None
    raw = m.group(1) or m.group(2)
    try:
        n = int(raw)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def enrich_source(
    *,
    index: int,
    title: str,
    rel_path: str,
    score: float,
    retrieval: str,
    text: str,
    asset_path: str = "",
) -> dict:
    page = extract_page_hint(text)
    slide = None
    m = re.search(r"---\s*幻灯片\s*(\d+)\s*---", text or "", re.I)
    if m:
        slide = int(m.group(1))
    open_path = asset_path or rel_path
    return {
        "index": index,
        "title": title,
        "path": rel_path,
        "score": score,
        "retrieval": retrieval,
        "asset_path": asset_path,
        "open_path": open_path,
        "page": page,
        "slide": slide,
    }


def source_open_label(src: dict) -> str:
    page = src.get("page")
    slide = src.get("slide")
    if page:
        return f"第 {page} 页"
    if slide:
        return f"幻灯片 {slide}"
    return "打开原文"


def sources_footer_html(sources: list[dict]) -> str:
    if not sources:
        return ""
    items: list[str] = []
    for s in sources:
        idx = s.get("index") or 0
        open_path = s.get("open_path") or s.get("asset_path") or s.get("path") or ""
        loc = ""
        if s.get("page"):
            loc = f' data-page="{int(s["page"])}"'
        elif s.get("slide"):
            loc = f' data-slide="{int(s["slide"])}"'
        label = source_open_label(s)
        path_hint = esc(s.get("path") or "")
        if open_path:
            items.append(
                f'<li class="cite-source-item">'
                f'<button type="button" class="cite-open" data-chunk="{idx}" '
                f'data-path="{esc(open_path)}"{loc}>{esc(label)}</button> '
                f'<span class="src-title">{esc(s.get("title") or "")}</span> '
                f'<span class="src-path">{path_hint}</span></li>'
            )
        else:
            items.append(
                f'<li><span class="src-title">{esc(s.get("title") or "")}</span> '
                f'<span class="src-path">{path_hint}</span></li>'
            )
    return f'<footer class="answer-sources"><h3>来源</h3><ul>{"".join(items)}</ul></footer>'


def linkify_fragment_refs(html: str, sources: list[dict]) -> str:
    """Turn 「片段 N」 in evidence section into open-source buttons when possible."""
    if not html or not sources:
        return html
    by_idx = {int(s.get("index") or 0): s for s in sources if s.get("index")}

    def repl(m: re.Match[str]) -> str:
        n = int(m.group(1))
        src = by_idx.get(n)
        if not src:
            return m.group(0)
        open_path = src.get("open_path") or src.get("asset_path") or src.get("path") or ""
        if not open_path:
            return m.group(0)
        page_attr = ""
        if src.get("page"):
            page_attr = f' data-page="{int(src["page"])}"'
        elif src.get("slide"):
            page_attr = f' data-slide="{int(src["slide"])}"'
        return (
            f'<button type="button" class="cite-open cite-inline" data-chunk="{n}" '
            f'data-path="{esc(open_path)}"{page_attr}>片段 {n}</button>'
        )

    return re.sub(r"片段\s*(\d+)", repl, html)
