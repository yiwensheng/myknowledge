"""知识库初始化清零。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def wiki(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "wiki"
    root.mkdir()
    (root / "notes").mkdir()
    (root / "notes" / "a.md").write_text("# a\n", encoding="utf-8")
    (root / ".rag").mkdir()
    (root / ".rag" / "chunks.json").write_text("[]", encoding="utf-8")
    (root / ".memory").mkdir()
    (root / ".config").mkdir()
    external = tmp_path / "external_docs"
    external.mkdir()
    (external / "keep.txt").write_text("keep", encoding="utf-8")
    linked = {
        "version": 1,
        "auto_index": True,
        "poll_seconds": 60,
        "dirs": [{"path": str(external), "label": "ext", "enabled": True}],
    }
    (root / ".config" / "linked-dirs.json").write_text(
        json.dumps(linked, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setenv("WIKI_ROOT", str(root))
    monkeypatch.setenv("MYKNOWLEDGE_ROOT", str(root))
    from lib import config

    config.load_dotenv()
    return root, external


def test_reset_requires_confirm(wiki):
    root, _ = wiki
    from lib.wiki_reset import CONFIRM_PHRASE, reset_wiki_knowledge

    bad = reset_wiki_knowledge(confirm="不对", root=root)
    assert bad["ok"] is False
    assert CONFIRM_PHRASE in bad["error"]
    assert (root / "notes" / "a.md").is_file()


def test_reset_clears_wiki_keeps_external(wiki):
    root, external = wiki
    from lib.wiki_reset import CONFIRM_PHRASE, reset_wiki_knowledge

    r = reset_wiki_knowledge(confirm=CONFIRM_PHRASE, root=root)
    assert r["ok"] is True
    assert not (root / "notes" / "a.md").exists()
    assert (root / "notes").is_dir()
    assert (root / "distill" / "skills" / "README.md").is_file()
    assert (external / "keep.txt").read_text(encoding="utf-8") == "keep"
    linked = json.loads((root / ".config" / "linked-dirs.json").read_text(encoding="utf-8"))
    assert linked.get("dirs") == []


def test_preview_lists_linked_untouched(wiki):
    root, external = wiki
    from lib.wiki_reset import preview_wiki_reset

    p = preview_wiki_reset(root)
    assert p["confirm_phrase"]
    assert any(str(external) in x for x in p["linked_external_paths_untouched"])
    assert "不可撤销" in p["disclaimer"]
