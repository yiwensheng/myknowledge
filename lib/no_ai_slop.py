"""no-ai-slop：写文章去 AI 味规则注入。"""

from __future__ import annotations

import os
from pathlib import Path

from .config import ROOT, load_dotenv

_RULES_PATH = ROOT / "skills" / "no-ai-slop" / "produce-rules.md"
_FALLBACK = """# 去 AI 味（写文章）
禁用：赋能、抓手、底层逻辑、闭环、对齐、沉淀、赛道、护城河、飞轮、方法论、综上所述。
禁止二元对立套话、伪洞察铺垫、重要性吹捧、模糊「专家表示」、伪深刻结尾。主动语态，具体写事实。"""


def no_ai_slop_enabled() -> bool:
    load_dotenv()
    raw = os.environ.get("MYKNOWLEDGE_NO_AI_SLOP", "1").strip().lower()
    return raw not in ("0", "false", "no")


def get_no_ai_slop_block() -> str:
    """Return produce-rules markdown for system prompt, or empty if disabled."""
    if not no_ai_slop_enabled():
        return ""
    if _RULES_PATH.is_file():
        text = _RULES_PATH.read_text(encoding="utf-8").strip()
        return text if text else _FALLBACK
    return _FALLBACK
