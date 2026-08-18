"""外联目录配置写入 wiki 可写路径。"""

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
    install = tmp_path / "install"
    install.mkdir()
    # Simulate read-only install tree .config
    (install / ".config").mkdir()
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / ".config").mkdir()
    monkeypatch.setenv("WIKI_ROOT", str(wiki))
    monkeypatch.setenv("MYKNOWLEDGE_ROOT", str(wiki))
    monkeypatch.setenv("YIZHI_APP_ROOT", str(install))
    # Force package ROOT to install for this process
    import lib.config as config
    import lib.linked_dirs as linked_dirs

    monkeypatch.setattr(config, "ROOT", install)
    monkeypatch.setattr(linked_dirs, "ROOT", install)
    monkeypatch.setattr(linked_dirs, "_LEGACY_CONFIG_FILE", install / ".config" / "linked-dirs.json")
    config.load_dotenv()
    return wiki, install


def test_add_linked_dir_writes_wiki_config(wiki, tmp_path):
    wiki_root, install = wiki
    ext = tmp_path / "docs"
    ext.mkdir()
    (ext / "a.txt").write_text("hi", encoding="utf-8")

    from lib.linked_dirs import add_linked_dir, config_file

    # Make install config unwritable to catch regression
    install_cfg = install / ".config"
    install_cfg.chmod(0o555)

    try:
        result = add_linked_dir(str(ext), label="测试")
    finally:
        install_cfg.chmod(0o755)

    assert result["active_count"] >= 1
    cfg = config_file(wiki_root)
    assert cfg.is_file()
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert any(str(ext.resolve()) in str(d.get("path")) for d in data.get("dirs") or [])


def test_migrate_from_legacy(wiki, tmp_path):
    wiki_root, install = wiki
    ext = tmp_path / "legacy_docs"
    ext.mkdir()
    legacy = {
        "version": 1,
        "auto_index": True,
        "poll_seconds": 60,
        "dirs": [{"path": str(ext), "label": "旧", "enabled": True}],
    }
    (install / ".config" / "linked-dirs.json").write_text(
        json.dumps(legacy, ensure_ascii=False), encoding="utf-8"
    )

    from lib.linked_dirs import config_file, list_linked_dirs

    data = list_linked_dirs()
    assert data["active_count"] >= 1
    assert config_file(wiki_root).is_file()
