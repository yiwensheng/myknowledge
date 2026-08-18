"""human-writing：写文章活人感 / 材料关 / 硬禁辞章注入。"""

from __future__ import annotations

import os
from pathlib import Path

from .config import ROOT, load_dotenv

_RULES_PATH = ROOT / "skills" / "human-writing" / "produce-rules.md"
_FALLBACK = """# 活人感写作（写文章）
事实只来自检索与用户补充；禁止编造亲历与假案例。
禁用冒号与破折号作叙事节奏；禁用「不是……而是……」等翻案句。
每段须推进事实或判断；不足则写待补充，勿凑字。"""


def human_writing_enabled() -> bool:
    load_dotenv()
    raw = os.environ.get("MYKNOWLEDGE_HUMAN_WRITING", "1").strip().lower()
    return raw not in ("0", "false", "no")


def get_human_writing_block() -> str:
    """Return produce-rules markdown for system prompt, or empty if disabled."""
    if not human_writing_enabled():
        return ""
    if _RULES_PATH.is_file():
        text = _RULES_PATH.read_text(encoding="utf-8").strip()
        return text if text else _FALLBACK
    return _FALLBACK
