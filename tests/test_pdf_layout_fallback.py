"""PDF layout fallback must not raise without ONNX models."""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.pdf_layout import extract_layout_table_blocks, pdf_layout_enabled, resolve_pdf_layout_dir


def test_layout_enabled_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MYKNOWLEDGE_PDF_LAYOUT", raising=False)
    assert pdf_layout_enabled() is True
    monkeypatch.setenv("MYKNOWLEDGE_PDF_LAYOUT", "off")
    assert pdf_layout_enabled() is False


def test_extract_layout_no_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYKNOWLEDGE_PDF_LAYOUT", "1")
    monkeypatch.setenv("MYKNOWLEDGE_PDF_LAYOUT_DIR", str(tmp_path / "missing_models"))
    # empty page texts → weak pages, but no PDF → still must not raise when path invalid handled upstream
    # create minimal 1-page PDF via reportlab
    from reportlab.pdfgen import canvas

    pdf = tmp_path / "blank.pdf"
    c = canvas.Canvas(str(pdf))
    c.drawString(72, 720, "hello")
    c.save()
    by_page, notices = extract_layout_table_blocks(pdf, [""], skip_pages=set())
    assert isinstance(by_page, dict)
    assert isinstance(notices, list)


def test_resolve_dir_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = tmp_path / "pdf_layout"
    d.mkdir()
    monkeypatch.setenv("MYKNOWLEDGE_PDF_LAYOUT_DIR", str(d))
    assert resolve_pdf_layout_dir() == d
