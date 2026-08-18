"""PDF 分栏阅读序启发式。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_multicolumn_left_then_right():
    from lib.extract import _blocks_to_multicolumn_text

    # 左栏 y=10/50，右栏 y=10/50，页宽 600，中间大空隙
    blocks = [
        (20, 10, 180, 30, "左上"),
        (320, 10, 480, 30, "右上"),
        (20, 50, 180, 70, "左下"),
        (320, 50, 480, 70, "右下"),
    ]
    text = _blocks_to_multicolumn_text(blocks, 600.0)
    assert text.index("左上") < text.index("左下") < text.index("右上") < text.index("右下")


def test_single_column_y_order():
    from lib.extract import _blocks_to_multicolumn_text

    blocks = [
        (20, 80, 200, 100, "第二"),
        (20, 10, 200, 30, "第一"),
    ]
    text = _blocks_to_multicolumn_text(blocks, 400.0)
    assert text.index("第一") < text.index("第二")


def test_pdf_caption_default_off(monkeypatch):
    from lib import extract

    monkeypatch.delenv("MYKNOWLEDGE_PDF_CAPTION", raising=False)
    assert extract._pdf_caption_enabled() is False
    monkeypatch.setenv("MYKNOWLEDGE_PDF_CAPTION", "1")
    assert extract._pdf_caption_enabled() is True
