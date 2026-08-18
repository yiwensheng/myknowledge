"""Parse-quality smoke check for document extract + RAG chunking."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .config import wiki_root
from .rag_chunk import chunk_document, is_markdown_table_block

_OCR_MARK = re.compile(r"(图\d+\s*OCR|扫描\s*OCR|OCR)", re.I)
_TABLE_MARK = re.compile(r"第\d+页-表格|^\|.+\|", re.M)
_MID_CELL_CUT = re.compile(r"\|[^|\n]*$")  # trailing open cell without closing |


def _sample_paths(root: Path, topic: str = "", limit: int = 8) -> list[Path]:
    topic = (topic or "").strip()
    if topic:
        p = Path(topic)
        if not p.is_absolute():
            p = root / topic
        if p.is_file():
            return [p]
        if p.is_dir():
            files = [x for x in p.rglob("*") if x.is_file()]
            return files[:limit]

    inbox = root / "inbox"
    candidates: list[Path] = []
    if inbox.is_dir():
        for x in sorted(inbox.rglob("*")):
            if not x.is_file():
                continue
            if "inbox-processed" in x.parts:
                continue
            if x.suffix.lower() in {".pdf", ".docx", ".doc", ".pptx", ".md", ".txt", ".png", ".jpg", ".jpeg"}:
                candidates.append(x)
            if len(candidates) >= limit:
                break
    if candidates:
        return candidates

    # fallback: recent notes/sources
    for d in ("notes", "sources", "distill/memory"):
        base = root / d
        if not base.is_dir():
            continue
        for x in sorted(base.rglob("*.md"), reverse=True):
            candidates.append(x)
            if len(candidates) >= limit:
                return candidates
    return candidates[:limit]


def _analyze_text(name: str, text: str) -> dict[str, Any]:
    text = text or ""
    chunks = chunk_document(text, title=name, size=480, overlap=80)
    issues: list[str] = []
    table_chunks = 0
    for ch in chunks:
        if is_markdown_table_block(ch):
            table_chunks += 1
            for ln in ch.splitlines():
                s = ln.strip()
                if not s or s.startswith("|---") or set(s) <= {"|", "-", ":", " "}:
                    continue
                if s.count("|") < 2 and s.startswith("|"):
                    issues.append("疑似表行被切断（管道符不成对）")
                    break
                if _MID_CELL_CUT.search(s) and not s.endswith("|"):
                    issues.append("疑似表单元格被截断")
                    break

    has_table = bool(_TABLE_MARK.search(text)) or table_chunks > 0
    has_ocr = bool(_OCR_MARK.search(text))
    emptyish = len(text.strip()) < 40

    if emptyish:
        issues.append("提取文本过短，可能解析失败或扫描件未 OCR")
    if has_table and table_chunks == 0 and "|" not in text:
        issues.append("原文提及表格但未见 Markdown 表结构")

    return {
        "chars": len(text),
        "chunks": len(chunks),
        "table_chunks": table_chunks,
        "has_table_signal": has_table,
        "has_ocr_signal": has_ocr,
        "issues": issues,
        "preview": text[:280].replace("\n", " "),
    }


def run_parse_quality_check(topic: str = "", root: Path | None = None, limit: int = 8) -> dict[str, Any]:
    """Smoke-check extract+chunk on sample files. topic=path or empty for inbox."""
    root = root or wiki_root()
    paths = _sample_paths(root, topic, limit=limit)
    if not paths:
        return {
            "ok": True,
            "action": "parse-check",
            "output": "# 解析质量抽检\n\n未找到可抽检文件。请把样本放入 inbox/，或传入相对/绝对路径。",
            "items": [],
        }

    from .extract import extract_text

    lines = ["# 解析质量抽检\n", f"样本数：{len(paths)}\n"]
    items: list[dict[str, Any]] = []
    for path in paths:
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = str(path)
        try:
            if path.suffix.lower() in {".md", ".txt"}:
                text = path.read_text(encoding="utf-8", errors="replace")
            else:
                text = extract_text(path)
            analysis = _analyze_text(path.stem, text)
            analysis["path"] = rel
            analysis["ok"] = True
        except Exception as e:
            analysis = {
                "path": rel,
                "ok": False,
                "chars": 0,
                "chunks": 0,
                "table_chunks": 0,
                "has_table_signal": False,
                "has_ocr_signal": False,
                "issues": [f"提取失败: {e}"],
                "preview": "",
            }
        items.append(analysis)
        flag = "⚠" if analysis.get("issues") or not analysis.get("ok") else "✓"
        lines.append(f"## {flag} `{analysis['path']}`")
        lines.append(
            f"- 字符 {analysis.get('chars', 0)} · 分块 {analysis.get('chunks', 0)} · "
            f"表块 {analysis.get('table_chunks', 0)} · "
            f"OCR信号 {'是' if analysis.get('has_ocr_signal') else '否'} · "
            f"表格信号 {'是' if analysis.get('has_table_signal') else '否'}"
        )
        for iss in analysis.get("issues") or []:
            lines.append(f"- 问题：{iss}")
        if analysis.get("preview"):
            lines.append(f"- 预览：{analysis['preview'][:200]}…")
        lines.append("")

    warn_n = sum(1 for it in items if it.get("issues") or not it.get("ok"))
    lines.insert(2, f"需关注：{warn_n}/{len(items)}\n")
    lines.append(
        "说明：人类读得懂的提取结果，检索才靠谱。"
        "复杂扫描/分栏/公式仍可能需本机 Tesseract 或后续增强；未内置 MinerU。"
    )
    return {"ok": True, "action": "parse-check", "output": "\n".join(lines), "items": items}
