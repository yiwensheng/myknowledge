"""Load persona and task prompts from prompts/ directory."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

from .config import ROOT, load_dotenv

DEFAULT_PROMPTS_DIR = ROOT / "prompts"


def prompts_dir() -> Path:
    load_dotenv()
    custom = os.environ.get("MYKNOWLEDGE_PROMPTS_DIR", "").strip()
    if custom:
        return Path(custom).expanduser().resolve()
    return DEFAULT_PROMPTS_DIR.resolve()


def _read_prompt(name: str, fallback: str = "") -> str:
    path = prompts_dir() / name
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        # Strip markdown heading line if file starts with # title
        lines = text.splitlines()
        if lines and lines[0].startswith("#"):
            lines = lines[1:]
        return "\n".join(lines).strip()
    return fallback.strip()


def _with_yizhi_product(base: str) -> str:
    from .yizhi_product import yizhi_product_block

    product = yizhi_product_block()
    if not product:
        return base
    return f"{base}\n\n---\n\n{product}"


def persona() -> str:
    from .persona_config import owner_context_for_prompt, persona_for_prompt

    custom = persona_for_prompt()
    if custom:
        return _with_yizhi_product(custom)
    owner = owner_context_for_prompt()
    if owner:
        base = _read_prompt("persona.md", "你是客观理性的知识库助手。")
        return _with_yizhi_product(f"{owner}\n\n---\n\n{base}")
    return _with_yizhi_product(
        _read_prompt("persona.md", "你是客观理性的知识库助手。")
    )


def invalidate_persona_cache() -> None:
    from .yizhi_product import invalidate_yizhi_product_cache

    invalidate_yizhi_product_cache()
    for fn in (system_for_ask, system_for_produce, system_for_deduce):
        if hasattr(fn, "_cache"):
            delattr(fn, "_cache")


def ask_task() -> str:
    return _read_prompt("ask.md", "根据检索片段回答问题，不足处说明缺口。")


def produce_task() -> str:
    return _read_prompt(
        "produce.md",
        "根据检索片段撰写结构化 Markdown 知识条目，不要 YAML frontmatter。",
    )


def deduce_task() -> str:
    return _read_prompt(
        "deduce.md",
        "基于检索片段撰写推演报告与关系图解读，不要 YAML frontmatter。",
    )


DEDUCE_REPORT_SECTIONS = """
## 已知事实
（仅引用检索片段，逐条标注来源路径）

## 可能走向
（2–4 条；每条标注依据强度：强/中/弱；无依据不写）

## 关键不确定因素

## 知识库缺口
"""

DEDUCE_GRAPH_SECTION = """
## 关系图解读
（针对本次子图：核心节点、带箭头的有向连边及其 label 含义、与推演主题的关联；箭头表示 source→target 的关系方向）
"""


def output_rules_block() -> str:
    from .output_rules import format_rules_block

    return format_rules_block()


def system_for_ask() -> str:
    from .dzs_framework import get_dzs_block
    from .writing_style import get_style_block

    cache = getattr(system_for_ask, "_cache", None)
    now = time.time()
    if cache and now - cache[0] < 30:
        return cache[1]

    style = get_style_block(refresh_if_stale=False)
    rules = output_rules_block()
    dzs = get_dzs_block()
    base = f"{persona()}\n\n---\n\n{ask_task()}"
    if rules:
        base = f"{base}\n\n---\n\n{rules}"
    if style:
        base = f"{base}\n\n---\n\n{style}"
    if dzs:
        base = f"{base}\n\n---\n\n{dzs}"
    system_for_ask._cache = (now, base)  # type: ignore[attr-defined]
    return base


def system_for_produce() -> str:
    from .basb_writing import get_basb_block
    from .de_ai_writing import get_de_ai_writing_block
    from .dzs_framework import get_dzs_block
    from .human_writing import get_human_writing_block
    from .no_ai_slop import get_no_ai_slop_block
    from .writing_style import get_style_block

    cache = getattr(system_for_produce, "_cache", None)
    now = time.time()
    if cache and now - cache[0] < 30:
        return cache[1]

    style = get_style_block(refresh_if_stale=False)
    rules = output_rules_block()
    human = get_human_writing_block()
    slop = get_no_ai_slop_block()
    dzs = get_dzs_block()
    basb = get_basb_block()
    de_ai = get_de_ai_writing_block()
    base = f"{persona()}\n\n---\n\n{produce_task()}"
    if rules:
        base = f"{base}\n\n---\n\n{rules}"
    if style:
        base = f"{base}\n\n---\n\n{style}"
    if human:
        base = f"{base}\n\n---\n\n{human}"
    if slop:
        base = f"{base}\n\n---\n\n{slop}"
    if de_ai:
        base = f"{base}\n\n---\n\n{de_ai}"
    if dzs:
        base = f"{base}\n\n---\n\n{dzs}"
    if basb:
        base = f"{base}\n\n---\n\n{basb}"
    system_for_produce._cache = (now, base)  # type: ignore[attr-defined]
    return base


def system_for_deduce() -> str:
    from .dzs_framework import get_dzs_block
    from .writing_style import get_style_block

    cache = getattr(system_for_deduce, "_cache", None)
    now = time.time()
    if cache and now - cache[0] < 30:
        return cache[1]

    style = get_style_block(refresh_if_stale=False)
    rules = output_rules_block()
    dzs = get_dzs_block()
    base = f"{persona()}\n\n---\n\n{deduce_task()}"
    if rules:
        base = f"{base}\n\n---\n\n{rules}"
    if style:
        base = f"{base}\n\n---\n\n{style}"
    if dzs:
        base = f"{base}\n\n---\n\n{dzs}"
    system_for_deduce._cache = (now, base)  # type: ignore[attr-defined]
    return base


def parse_wiki_hints(content: str) -> tuple[str, str, list[str]]:
    """Extract <!-- wiki-type --> and <!-- wiki-tags --> from model output."""
    wiki_type = "concept"
    tags: list[str] = []
    m_type = re.search(r"<!--\s*wiki-type:\s*(\w+)\s*-->", content)
    if m_type:
        wiki_type = m_type.group(1).strip()
    m_tags = re.search(r"<!--\s*wiki-tags:\s*(.+?)\s*-->", content)
    if m_tags:
        tags = [t.strip() for t in m_tags.group(1).split(",") if t.strip()]
    # Remove HTML comments from body
    body = re.sub(r"<!--\s*wiki-type:.+?-->\s*", "", content)
    body = re.sub(r"<!--\s*wiki-tags:.+?-->\s*", "", body)
    return wiki_type, body.strip(), tags


def title_from_markdown(body: str, fallback: str) -> str:
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return fallback
