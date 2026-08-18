"""Markdown to HTML for GUI produce output."""

from __future__ import annotations

import markdown as md_lib


def markdown_to_html(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return '<p class="hint">（无内容）</p>'
    if text.lstrip().startswith("<"):
        return f'<article class="produce-article">{text}</article>'
    body = md_lib.markdown(
        text,
        extensions=["extra", "sane_lists", "nl2br"],
        output_format="html5",
    )
    return f'<article class="produce-article">{body}</article>'
