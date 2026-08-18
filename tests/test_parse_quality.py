"""Parse quality smoke check."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_parse_quality_on_md(tmp_path: Path, monkeypatch):
    root = tmp_path / "wiki"
    inbox = root / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "sample.md").write_text(
        "# Hi\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n\n正文。\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("WIKI_ROOT", str(root))
    from lib.parse_quality import run_parse_quality_check

    r = run_parse_quality_check()
    assert r["ok"]
    assert r["items"]
    assert "解析质量抽检" in r["output"]
