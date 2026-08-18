"""Markdown-aware document chunking for RAG (inspired by heading/paragraph splits)."""

from __future__ import annotations

import re

_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
_PAGE_MARK_RE = re.compile(r"^---\s*第\d+页\s*---\s*$", re.MULTILINE)
_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_markdown_table_block(text: str) -> bool:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return False
    pipe_lines = sum(1 for ln in lines if "|" in ln)
    return pipe_lines >= 2 and pipe_lines >= max(2, len(lines) // 2)


def is_html_table_block(text: str) -> bool:
    t = (text or "").lower()
    return "<table" in t and "</table>" in t and ("<tr" in t or "<th" in t or "<td" in t)


def _chunk_html_table(text: str, size: int) -> list[str]:
    """按 <tr> 切分 HTML 表，避免切断单元格；每块尽量带上开头的 <table>…首行。"""
    text = text.strip()
    if len(text) <= size:
        return [text]
    rows = re.findall(r"<tr\b.*?</tr>", text, flags=re.I | re.DOTALL)
    if len(rows) < 2:
        return [text]
    open_m = re.search(r"<table\b[^>]*>", text, flags=re.I)
    close_m = re.search(r"</table>", text, flags=re.I)
    open_tag = open_m.group(0) if open_m else "<table>"
    close_tag = "</table>"
    header = rows[0]
    body = rows[1:]
    pieces: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        if not buf:
            return
        block = open_tag + header + "".join(buf) + close_tag
        pieces.append(block.strip())
        buf = []

    for row in body:
        candidate = open_tag + header + "".join(buf + [row]) + close_tag
        if buf and len(candidate) > size:
            flush()
            solo = open_tag + header + row + close_tag
            if len(solo) > size:
                pieces.append(solo.strip())
            else:
                buf = [row]
        else:
            buf.append(row)
    flush()
    return pieces or [text]


def _table_header_rows(lines: list[str]) -> list[str]:
    """Return header + separator rows when present; else first row only."""
    if not lines:
        return []
    if len(lines) >= 2 and _TABLE_SEP_RE.match(lines[1].strip()):
        return [lines[0], lines[1]]
    return [lines[0]]


def _chunk_markdown_table(text: str, size: int) -> list[str]:
    """Split a GFM table by rows only; never cut mid-row. Repeat header on each piece."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    if len(text) <= size:
        return [text.strip()]

    header = _table_header_rows(lines)
    body = lines[len(header) :]
    if not body:
        return ["\n".join(header)] if header else [text.strip()]

    pieces: list[str] = []
    buf_rows: list[str] = []
    header_block = "\n".join(header)

    def flush() -> None:
        nonlocal buf_rows
        if not buf_rows:
            return
        block = header_block + "\n" + "\n".join(buf_rows) if header_block else "\n".join(buf_rows)
        pieces.append(block.strip())
        buf_rows = []

    for row in body:
        candidate_rows = buf_rows + [row]
        candidate = (
            header_block + "\n" + "\n".join(candidate_rows) if header_block else "\n".join(candidate_rows)
        )
        if buf_rows and len(candidate) > size:
            flush()
            solo = header_block + "\n" + row if header_block else row
            if len(solo) > size:
                pieces.append(solo.strip())
            else:
                buf_rows = [row]
        else:
            buf_rows = candidate_rows
    flush()
    return pieces or [text.strip()]


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Return (heading_label, body) sections; first section may have empty heading."""
    text = _normalize(text)
    if not text:
        return []
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [("", text)]
    sections: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        lead = text[: matches[0].start()].strip()
        if lead:
            sections.append(("", lead))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        heading = m.group(2).strip()
        body = text[start:end].strip()
        if body:
            sections.append((heading, body))
    return sections


def _split_paragraphs(block: str) -> list[str]:
    # 先抽出完整 HTML 表，避免按空行切开 <tr>
    held: list[str] = []

    def _hold(m: re.Match[str]) -> str:
        held.append(m.group(0))
        return f"\n\n@@HTMLTABLE{len(held) - 1}@@\n\n"

    block = re.sub(r"<table\b.*?</table>", _hold, block, flags=re.I | re.DOTALL)
    parts = re.split(r"\n\s*\n", block)
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        m = re.fullmatch(r"@@HTMLTABLE(\d+)@@", p)
        if m:
            out.append(held[int(m.group(1))])
            continue
        if _PAGE_MARK_RE.match(p):
            out.append(p)
            continue
        if p.startswith("|") and "|" in p[1:]:
            out.append(p)
            continue
        out.append(p)
    return out


def _merge_small(parts: list[str], min_len: int) -> list[str]:
    if not parts:
        return []
    merged: list[str] = []
    buf = ""
    for p in parts:
        if not buf:
            buf = p
            continue
        if (
            is_markdown_table_block(buf)
            or is_markdown_table_block(p)
            or is_html_table_block(buf)
            or is_html_table_block(p)
        ):
            merged.append(buf)
            buf = p
            continue
        if len(buf) < min_len and len(buf) + len(p) + 2 <= min_len * 3:
            buf = f"{buf}\n\n{p}"
        else:
            merged.append(buf)
            buf = p
    if buf:
        merged.append(buf)
    return merged


def _window_chunks(text: str, size: int, overlap: int) -> list[str]:
    if is_html_table_block(text):
        return _chunk_html_table(text, size)
    if is_markdown_table_block(text):
        return _chunk_markdown_table(text, size)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def chunk_document(
    text: str,
    *,
    title: str = "",
    size: int = 480,
    overlap: int = 80,
) -> list[str]:
    """Split document into RAG chunks respecting headings, paragraphs, and table rows."""
    text = _normalize(text)
    if not text:
        return []
    if title and title not in text[:80]:
        text = f"{title}\n\n{text}"

    sections = _split_sections(text)
    pieces: list[str] = []
    min_para = max(120, size // 4)

    for heading, body in sections:
        prefix = f"【{heading}】\n" if heading else ""
        for para in _merge_small(_split_paragraphs(body), min_para):
            if is_html_table_block(para):
                table_chunks = _chunk_html_table(para, max(80, size - len(prefix)))
                for tc in table_chunks:
                    pieces.append(prefix + tc if prefix else tc)
                continue
            if is_markdown_table_block(para):
                table_chunks = _chunk_markdown_table(para, max(80, size - len(prefix)))
                for i, tc in enumerate(table_chunks):
                    if prefix and i == 0:
                        pieces.append(f"{prefix}{tc}".strip())
                    else:
                        pieces.append(tc.strip())
                continue
            block = f"{prefix}{para}" if prefix else para
            if len(block) <= size:
                pieces.append(block.strip())
            else:
                pieces.extend(_window_chunks(block, size, overlap))

    if not pieces and text:
        pieces = _window_chunks(text, size, overlap)
    return [p for p in pieces if p.strip()]


def chunk_document_parent_child(
    text: str,
    *,
    title: str = "",
    parent_size: int = 960,
    child_size: int = 320,
    overlap: int = 80,
) -> list[dict[str, str]]:
    """Parent-child chunking: index children, return parent text for LLM context.

    Each item: ``{"text": child, "parent_text": parent, "parent_id": id}``.
    """
    parents = chunk_document(text, title=title, size=parent_size, overlap=overlap)
    if not parents:
        return []
    child_size = max(120, min(child_size, parent_size))
    child_overlap = max(0, min(overlap, child_size // 2))
    out: list[dict[str, str]] = []
    for pi, parent in enumerate(parents):
        parent_id = f"p{pi}"
        children = chunk_document(parent, title="", size=child_size, overlap=child_overlap)
        if not children:
            children = [parent]
        for child in children:
            out.append(
                {
                    "text": child,
                    "parent_text": parent,
                    "parent_id": parent_id,
                }
            )
    return out
