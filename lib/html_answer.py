"""HTML templates for ask answers (no Markdown)."""

from __future__ import annotations

import html
import html as html_mod
import re


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def html_to_plain(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"</li>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_mod.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def no_ground_html(question: str) -> str:
    q = esc(question)
    return (
        '<div class="answer answer-empty">'
        '<p class="lead">知识库中暂无足够信息，无法基于库内事实回答该问题。</p>'
        f'<p class="hint">建议：将相关资料放入 <code>inbox/</code> 后执行整理，'
        f"或补充与「{q}」相关的文档后再提问。</p>"
        "</div>"
    )


def sources_footer_html(sources: list[dict]) -> str:
    if not sources:
        return ""
    items = "".join(
        f'<li><span class="src-title">{esc(s.get("title") or "")}</span>'
        f' <span class="src-path">{esc(s.get("path") or "")}</span></li>'
        for s in sources
    )
    return f'<footer class="answer-sources"><h3>来源</h3><ul>{items}</ul></footer>'
