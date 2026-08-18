"""DZS 万能提示词框架：提问 / 写文章 / 推演认知催化注入。"""

from __future__ import annotations

import os
from pathlib import Path

from .config import ROOT, load_dotenv

_RULES_PATH = ROOT / "skills" / "dzs-prompt-framework" / "yizhi-rules.md"
_FALLBACK = """# DZS 认知催化（易知）
对提问/写文章/推演在内部静默做意图解构与三维压力测试（反常识、专家边界、创新性），再输出成品。
事实只许来自检索片段；禁止编造；禁止输出阶段过程或脉令 JSON。
简短事实问用快速档；写文章与推演默认标准或深度。"""


def dzs_enabled() -> bool:
    load_dotenv()
    raw = os.environ.get("MYKNOWLEDGE_DZS", "1").strip().lower()
    return raw not in ("0", "false", "no")


def get_dzs_block() -> str:
    """Return yizhi-rules markdown for system prompt, or empty if disabled."""
    if not dzs_enabled():
        return ""
    if _RULES_PATH.is_file():
        text = _RULES_PATH.read_text(encoding="utf-8").strip()
        return text if text else _FALLBACK
    return _FALLBACK
