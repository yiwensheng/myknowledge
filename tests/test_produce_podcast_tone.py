"""播客体例语气：亲切自然、过渡顺畅。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_podcast_genre_warm_transitions():
    from lib.produce_genres import format_genre_block, get_genre

    g = get_genre("podcast")
    outline = g.get("outline") or ""
    assert "亲切" in outline or "温暖" in outline
    assert "过渡" in outline
    block = format_genre_block("podcast")
    assert "播客" in block
    assert "主持人" in block
