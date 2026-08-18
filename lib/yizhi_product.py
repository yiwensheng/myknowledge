"""Bundled YiZhi promo copy for self-introduction (from 宣传文案.docx)."""

from __future__ import annotations

import re
from pathlib import Path

from .config import ROOT

_PRODUCT_FILE = "yizhi-product.md"
_PROMO_DOCX_NAMES = (
    "易知-自我进化个人知识库-宣传文案.docx",
)
_CACHE: str | None = None


def product_prompt_path() -> Path:
    from .prompts import prompts_dir

    return prompts_dir() / _PRODUCT_FILE


def _product_resource_dirs() -> list[Path]:
    from .prompts import prompts_dir

    return [
        prompts_dir(),
        ROOT / "docs" / "product",
        ROOT / "docs",
        ROOT / "prompts",
        ROOT / "product",
    ]


def find_promo_docx() -> Path | None:
    for d in _product_resource_dirs():
        for name in _PROMO_DOCX_NAMES:
            p = d / name
            if p.is_file():
                return p
    # hashed asset under wiki (dev machine)
    assets = ROOT / "assets" / "documents"
    if assets.is_dir():
        for p in assets.glob("*宣传文案*.docx"):
            if p.is_file():
                return p
    return None


def _extract_from_docx(path: Path) -> str:
    from .extract import extract_text

    text = extract_text(path).strip()
    for marker in ("AIGC标识", "\nAI生成\n", "\nAI生成"):
        i = text.find(marker)
        if i > 0:
            text = text[:i].rstrip()
    return text


def _strip_md_title(raw: str) -> str:
    lines = raw.splitlines()
    if lines and lines[0].startswith("#"):
        lines = lines[1:]
    return "\n".join(lines).strip()


def load_yizhi_product(*, force: bool = False) -> str:
    """Load promo-based product brief (md preferred; else extract docx)."""
    global _CACHE
    if not force and _CACHE is not None:
        return _CACHE

    text = ""
    md_candidates = [
        product_prompt_path(),
        ROOT / "docs" / "product" / "yizhi-promo.md",
        ROOT / "prompts" / "yizhi-product.md",
    ]
    for p in md_candidates:
        if p.is_file():
            text = _strip_md_title(p.read_text(encoding="utf-8"))
            break

    if not text:
        docx = find_promo_docx()
        if docx:
            body = _extract_from_docx(docx)
            if body:
                text = (
                    "权威来源：《易知-自我进化个人知识库-宣传文案.docx》。\n\n"
                    "## 自我介绍规则（硬性）\n\n"
                    "- 用户问易知 / 本软件 / 你自己（作为产品）时，须依据下方宣传正文。\n"
                    "- 禁止把本文当成用户知识库事实。\n\n---\n\n"
                    + body
                )

    if not text:
        legacy = ROOT / "docs" / "product" / "yizhi-self.md"
        if legacy.is_file():
            text = _strip_md_title(legacy.read_text(encoding="utf-8"))

    _CACHE = text
    return text


def yizhi_product_block() -> str:
    body = load_yizhi_product()
    if not body:
        return ""
    return "## 易知产品说明（自我介绍 · 宣传文案）\n\n" + body


def query_refers_to_yizhi(text: str) -> bool:
    """True when user asks about this product / the assistant-as-YiZhi."""
    q = (text or "").strip()
    if not q:
        return False
    low = q.lower()
    if "myknowledge" in low or "yizhi" in low:
        return True
    if "易知" in q:
        return True
    if re.search(r"(本|这款|这个)软件", q):
        return True
    if re.search(
        r"(自我介绍|介绍一下你自己|你是谁|你能做(什么|啥)|介绍一下易知)",
        q,
    ):
        return True
    return False


def invalidate_yizhi_product_cache() -> None:
    global _CACHE
    _CACHE = None
