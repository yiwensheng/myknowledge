# -*- coding: utf-8 -*-
"""Generate tiny PDF fixtures and verify PDF OCR extract path.

Usage:
  set PYTHONPATH=E:\\app\\Myknowledge
  python scripts/verify_pdf_ocr.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402


def _make_text_pdf(path: Path, text: str) -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=400, height=300)
    page.insert_text((40, 80), text, fontsize=14)
    doc.save(path)
    doc.close()


def _make_scan_pdf(path: Path, text: str) -> None:
    """Page with almost no text layer — content only as raster image."""
    import fitz

    img = Image.new("RGB", (600, 200), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    draw.text((30, 70), text, fill="black", font=font)
    buf = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    png = Path(buf.name)
    buf.close()
    img.save(png)

    doc = fitz.open()
    page = doc.new_page(width=600, height=200)
    page.insert_image(page.rect, filename=str(png))
    doc.save(path)
    doc.close()
    png.unlink(missing_ok=True)


def _make_mixed_pdf(path: Path) -> None:
    """Text layer + large embedded image with different OCR-able text."""
    import fitz

    img = Image.new("RGB", (400, 160), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 26)
    except OSError:
        font = ImageFont.load_default()
    draw.text((20, 50), "EMBEDDED_IMG_TOKEN_YZ99", fill="black", font=font)
    buf = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    png = Path(buf.name)
    buf.close()
    img.save(png)

    doc = fitz.open()
    page = doc.new_page(width=500, height=500)
    page.insert_text((40, 60), "TEXT_LAYER_TOKEN_YZ88 " * 3, fontsize=12)
    page.insert_image(fitz.Rect(40, 120, 440, 280), filename=str(png))
    doc.save(path)
    doc.close()
    png.unlink(missing_ok=True)


def main() -> int:
    from lib.extract import extract_text

    td = Path(tempfile.mkdtemp(prefix="yizhi-pdf-ocr-"))
    text_pdf = td / "text.pdf"
    scan_pdf = td / "scan.pdf"
    mixed_pdf = td / "mixed.pdf"

    _make_text_pdf(
        text_pdf,
        "Hello text layer only for unit check. Enough chars to skip scan OCR path.",
    )
    _make_scan_pdf(scan_pdf, "SCAN_PAGE_TOKEN_YZ77")
    _make_mixed_pdf(mixed_pdf)

    t1 = extract_text(text_pdf)
    t2 = extract_text(scan_pdf)
    t3 = extract_text(mixed_pdf)

    print("=== text.pdf ===")
    print(t1[:400])
    print("=== scan.pdf ===")
    print(t2[:600])
    print("=== mixed.pdf ===")
    print(t3[:800])

    ok = True
    if "第1页" not in t1:
        print("FAIL text: missing page mark")
        ok = False
    if "扫描 OCR" in t1:
        print("FAIL text: unexpected 扫描 OCR on rich text page")
        ok = False
    else:
        print("OK text (no scan OCR)")
    compact2 = "".join(t2.split())
    if "YZ77" not in compact2:
        print("FAIL scan: OCR token not found")
        ok = False
    else:
        print("OK scan")
    if "TEXT_LAYER_TOKEN_YZ88" not in t3:
        print("FAIL mixed: text layer missing")
        ok = False
    compact3 = "".join(t3.split())
    if "YZ99" not in compact3 and "EMBEDDED" not in compact3:
        print("WARN mixed: embedded OCR token weak/missing")
    else:
        print("OK mixed embedded OCR")
    print("tmpdir", td)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
