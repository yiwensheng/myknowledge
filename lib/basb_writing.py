"""BASB / 第二大脑：写文章与蒸馏的知识复用原则注入。"""

from __future__ import annotations

import os
from pathlib import Path

from .config import ROOT, load_dotenv

_RULES_PATH = ROOT / "skills" / "basb-writing" / "yizhi-rules.md"
_FALLBACK = """# BASB 知识复用（易知）
写文章前在内部用检索片段排 5～8 条思想群岛再展开；蒸馏时渐进加价值、沉淀可复用中间包。
事实只许来自检索；勿把过程文写入正文。"""


def basb_enabled() -> bool:
    load_dotenv()
    raw = os.environ.get("MYKNOWLEDGE_BASB", "1").strip().lower()
    return raw not in ("0", "false", "no")


def get_basb_block() -> str:
    if not basb_enabled():
        return ""
    if _RULES_PATH.is_file():
        text = _RULES_PATH.read_text(encoding="utf-8").strip()
        return text if text else _FALLBACK
    return _FALLBACK
