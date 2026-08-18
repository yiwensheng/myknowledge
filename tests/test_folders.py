"""资料夹 CRUD 与 RAG scope 展开。"""

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
    (root / "assets").mkdir()
    (root / ".config").mkdir()
    monkeypatch.setenv("WIKI_ROOT", str(root))
    monkeypatch.setenv("MYKNOWLEDGE_ROOT", str(root))
    from lib import config

    config.load_dotenv()
    return root


def test_ensure_default_folders(wiki: Path):
    from lib.folders import ensure_default_folders, list_folders

    ensure_default_folders()
    names = [f["name"] for f in list_folders()]
    assert "工作" in names
    assert "学习" in names
    assert "生活" in names
    cfg = json.loads((wiki / ".config" / "folders.json").read_text(encoding="utf-8"))
    assert cfg["version"] == 1
    assert len(cfg["folders"]) >= 3


def test_folder_crud(wiki: Path):
    from lib.folders import create_folder, delete_folder, list_folders, update_folder

    ensure = __import__("lib.folders", fromlist=["ensure_default_folders"]).ensure_default_folders
    ensure()
    created = create_folder("客户A")
    assert created["name"] == "客户A"
    assert created["id"]
    updated = update_folder(created["id"], name="客户甲")
    assert updated["name"] == "客户甲"
    delete_folder(created["id"])
    assert created["id"] not in {f["id"] for f in list_folders()}


def test_expand_folder_ids_to_scope_paths(wiki: Path):
    from lib.folders import create_folder, ensure_default_folders, expand_folder_ids_to_scope_paths
    from lib.memos import create_memo
    from lib.wiki import save_page

    ensure_default_folders()
    work = next(f for f in __import__("lib.folders", fromlist=["list_folders"]).list_folders() if f["name"] == "工作")
    create_memo("闪念 #工作\n内容", folder_ids=[work["id"]])
    save_page("note", "例会纪要", "正文", extra_meta={"folder_ids": [work["id"]]})
    paths = expand_folder_ids_to_scope_paths([work["id"]])
    assert any(p.startswith("notes/") for p in paths)
    assert len(paths) >= 1


def test_create_memo_requires_content(wiki: Path):
    from lib.memos import create_memo

    with pytest.raises(ValueError):
        create_memo("   ")


def test_create_memo_with_folders(wiki: Path):
    from lib.folders import ensure_default_folders, list_folders
    from lib.memos import create_memo, memo_to_dict

    ensure_default_folders()
    fid = list_folders()[0]["id"]
    page = create_memo("今天上午参加培训", folder_ids=[fid])
    d = memo_to_dict(page)
    assert d["folder_ids"] == [fid]
    assert "培训" in d["body"]
