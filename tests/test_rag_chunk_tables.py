"""RAG chunking: heading split + table row safety."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.rag_chunk import chunk_document, is_markdown_table_block


def test_is_markdown_table_block():
    table = "| a | b |\n| --- | --- |\n| 1 | 2 |\n"
    assert is_markdown_table_block(table)
    assert not is_markdown_table_block("just text\nmore text")


def test_table_not_cut_mid_row():
    header = "| col1 | col2 | col3 |\n| --- | --- | --- |\n"
    rows = [f"| r{i}aaaaaaaa | bbbbbbbbb | ccccccccc |\n" for i in range(20)]
    text = header + "".join(rows)
    chunks = chunk_document(text, size=120, overlap=20)
    assert len(chunks) >= 2
    for ch in chunks:
        for ln in ch.splitlines():
            s = ln.strip()
            if not s or set(s.replace("|", "").replace("-", "").replace(":", "").replace(" ", "")) == set():
                continue
            if "|" in s:
                assert s.startswith("|") and s.endswith("|"), f"mid-cut row: {s!r}"


def test_heading_still_respected():
    text = "# Title\n\nPara one is long enough to stand alone here.\n\n## Sec\n\nSecond paragraph content.\n"
    chunks = chunk_document(text, size=200, overlap=20)
    assert any("Title" in c or "【Title】" in c or "Sec" in c for c in chunks)
