"""ParseBench 风格 LLM 版面解析：清洗与分块（不调真实 LLM）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SAMPLE = """
```html
<div data-label="Title" data-bbox="10,10,900,80">采购订单</div>
<div data-label="Page-header" data-bbox="0,0,1000,40">页眉忽略</div>
<div data-label="Table" data-bbox="50,100,950,600">
<table>
<tr><th colspan="2">品名</th><th>数量</th></tr>
<tr><td>A</td><td>型</td><td>2</td></tr>
<tr><td>B</td><td>型</td><td>3</td></tr>
</table>
</div>
<div data-label="Text" data-bbox="50,620,900,700">备注：加急</div>
```
"""


def test_clean_keeps_html_table_drops_header():
    from lib.pdf_llm_parse import clean_llm_parse_html

    out = clean_llm_parse_html(SAMPLE)
    assert "采购订单" in out or "# 采购订单" in out
    assert "<table" in out.lower()
    assert "colspan" in out.lower()
    assert "页眉忽略" not in out
    assert "加急" in out


def test_html_table_chunk_by_tr():
    from lib.rag_chunk import chunk_document, is_html_table_block

    table = (
        "<table>"
        + "<tr><th>a</th><th>b</th></tr>"
        + "".join(f"<tr><td>r{i}</td><td>{i}</td></tr>" for i in range(20))
        + "</table>"
    )
    assert is_html_table_block(table)
    chunks = chunk_document(table, size=120)
    assert len(chunks) >= 2
    assert all("<table" in c.lower() for c in chunks)
    assert all("</table>" in c.lower() for c in chunks)
    # 不应从单元格中间切断标签
    assert not any(c.rstrip().endswith("<td>r") for c in chunks)


def test_pdf_llm_parse_default_off(monkeypatch):
    from lib import pdf_llm_parse

    monkeypatch.delenv("MYKNOWLEDGE_PDF_LLM_PARSE", raising=False)
    assert pdf_llm_parse.pdf_llm_parse_enabled() is False
    monkeypatch.setenv("MYKNOWLEDGE_PDF_LLM_PARSE", "1")
    assert pdf_llm_parse.pdf_llm_parse_enabled() is True
