"""Tests for digital PDF table → Markdown extraction."""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.pdf_tables import extract_tables_markdown, format_table_blocks, pdf_tables_enabled


def _make_table_pdf(path: Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

    doc = SimpleDocTemplate(str(path), pagesize=A4)
    data = [
        ["Clause", "Content"],
        ["Article3", "Penalty is 10% of contract"],
        ["Article5", "Arbitration"],
    ]
    t = Table(data, colWidths=[80, 300])
    t.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ]
        )
    )
    doc.build([t])


def test_pdf_tables_enabled_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MYKNOWLEDGE_PDF_TABLES", raising=False)
    assert pdf_tables_enabled() is True
    monkeypatch.setenv("MYKNOWLEDGE_PDF_TABLES", "0")
    assert pdf_tables_enabled() is False


def test_extract_tables_markdown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYKNOWLEDGE_PDF_TABLES", "1")
    pdf = tmp_path / "contract.pdf"
    _make_table_pdf(pdf)
    tables = extract_tables_markdown(pdf)
    assert tables, "expected at least one table"
    page_no, md = tables[0]
    assert page_no == 1
    assert "|" in md
    assert "Clause" in md or "Article3" in md or "10%" in md
    blocks = format_table_blocks(tables)
    assert 1 in blocks
    assert "第1页-表格1" in blocks[1][0]


def test_extract_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYKNOWLEDGE_PDF_TABLES", "0")
    pdf = tmp_path / "contract.pdf"
    _make_table_pdf(pdf)
    assert extract_tables_markdown(pdf) == []
