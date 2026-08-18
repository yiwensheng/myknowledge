"""去 AI 味增强包：Humanizer-zh / 说人话 / de-AI 蒸馏注入（写文章）。"""

from __future__ import annotations

import os
from pathlib import Path

from .config import ROOT, load_dotenv

_RULES_PATH = ROOT / "skills" / "de-ai-writing" / "produce-rules.md"
_FALLBACK = """# 去 AI 味增强
禁讲义腔与协作口吻；路标词少用；勿夸大「标志着/至关重要」；公众号用具体主语，砍翻译腔与表演洞察。"""


def de_ai_writing_enabled() -> bool:
    load_dotenv()
    raw = os.environ.get("MYKNOWLEDGE_DE_AI_WRITING", "1").strip().lower()
    return raw not in ("0", "false", "no")


def get_de_ai_writing_block() -> str:
    if not de_ai_writing_enabled():
        return ""
    if _RULES_PATH.is_file():
        text = _RULES_PATH.read_text(encoding="utf-8").strip()
        return text if text else _FALLBACK
    return _FALLBACK
