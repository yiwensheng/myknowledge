"""Digital PDF table extraction → Markdown (pdfplumber)."""

from __future__ import annotations

import os
import re
from pathlib import Path


def pdf_tables_enabled() -> bool:
    """MYKNOWLEDGE_PDF_TABLES 默认开启；显式 0/false/off 关闭。"""
    v = (os.environ.get("MYKNOWLEDGE_PDF_TABLES") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _cell_text(val: object) -> str:
    if val is None:
        return ""
    s = str(val).replace("\r\n", "\n").replace("\r", "\n").strip()
    s = re.sub(r"\s+", " ", s)
    return s.replace("|", "\\|")


def _rows_to_markdown(rows: list[list[object]]) -> str:
    cleaned: list[list[str]] = []
    for row in rows:
        if not row:
            continue
        cells = [_cell_text(c) for c in row]
        if not any(cells):
            continue
        cleaned.append(cells)
    if not cleaned:
        return ""
    width = max(len(r) for r in cleaned)
    for r in cleaned:
        while len(r) < width:
            r.append("")
    header = cleaned[0]
    body = cleaned[1:] if len(cleaned) > 1 else []
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    if not body:
        # single-row table: duplicate header as data-less still useful? keep only header+sep
        pass
    else:
        for r in body:
            lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def extract_tables_markdown(path: Path) -> list[tuple[int, str]]:
    """
    Return list of (1-based page_no, markdown_table).
    Empty list if disabled / pdfplumber missing / no tables.
    """
    if not pdf_tables_enabled():
        return []
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        return []

    out: list[tuple[int, str]] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for i, page in enumerate(pdf.pages):
                page_no = i + 1
                tables = None
                try:
                    tables = page.extract_tables() or []
                except Exception:
                    tables = []
                if not tables:
                    try:
                        found = page.find_tables() or []
                        tables = [t.extract() for t in found]
                    except Exception:
                        tables = []
                k = 0
                for raw in tables:
                    if not raw:
                        continue
                    md = _rows_to_markdown(raw)
                    if not md:
                        continue
                    k += 1
                    out.append((page_no, md))
    except Exception:
        return []
    return out


def format_table_blocks(tables: list[tuple[int, str]]) -> dict[int, list[str]]:
    """page_no → list of labeled markdown blocks."""
    by_page: dict[int, list[str]] = {}
    counters: dict[int, int] = {}
    for page_no, md in tables:
        counters[page_no] = counters.get(page_no, 0) + 1
        k = counters[page_no]
        block = f"--- 第{page_no}页-表格{k} ---\n{md}"
        by_page.setdefault(page_no, []).append(block)
    return by_page
