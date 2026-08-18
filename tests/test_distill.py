"""自我蒸馏骨架与解析。"""

from __future__ import annotations

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
    monkeypatch.setenv("WIKI_ROOT", str(root))
    monkeypatch.setenv("MYKNOWLEDGE_ROOT", str(root))
    from lib import config

    config.load_dotenv()
    return root


def test_ensure_distill_skeleton_idempotent(wiki: Path):
    from lib.distill import ensure_distill_skeleton

    r1 = ensure_distill_skeleton()
    assert (wiki / "distill" / "memory" / "README.md").is_file()
    assert (wiki / "distill" / "skills" / "README.md").is_file()
    assert (wiki / "distill" / "principle" / "README.md").is_file()
    assert (wiki / "distill" / "meta" / "蒸馏规则.md").is_file()
    assert r1["created"]

    custom = wiki / "distill" / "skills" / "my-skill.md"
    custom.write_text("# mine\n", encoding="utf-8")
    meta = wiki / "distill" / "meta" / "蒸馏规则.md"
    meta.write_text("# custom meta\n", encoding="utf-8")

    r2 = ensure_distill_skeleton()
    assert r2["created"] == []
    assert custom.read_text(encoding="utf-8") == "# mine\n"
    assert meta.read_text(encoding="utf-8") == "# custom meta\n"


def test_parse_distill_output():
    from lib.distill import _parse_distill_output, _is_empty_principle

    raw = """
<<<MEMORY>>>
做了列表迭代，缺权限校验。
<<<SKILL_TITLE>>>
列表拆解
<<<SKILL_BODY>>>
- 搜索筛选
- 批量操作
<<<PRINCIPLE_TITLE>>>
无
<<<PRINCIPLE_BODY>>>
无
"""
    p = _parse_distill_output(raw)
    assert "权限" in p["memory"]
    assert p["skill_title"] == "列表拆解"
    assert "搜索筛选" in p["skill_body"]
    assert _is_empty_principle(p["principle_title"], p["principle_body"])


def test_parse_topic_commit():
    from lib.distill import _parse_topic_commit

    t, c = _parse_topic_commit("正文\n确认入库", None)
    assert c is True and t == "正文"
    t2, c2 = _parse_topic_commit("仅预览", None)
    assert c2 is False and t2 == "仅预览"
    t3, c3 = _parse_topic_commit("x\n确认入库", False)
    assert c3 is False and "确认入库" not in t3
    t4, c4 = _parse_topic_commit("仅预览", True)
    assert c4 is True


def test_preview_markdown_mentions_confirm():
    from lib.distill import _preview_markdown

    md = _preview_markdown(
        {
            "memory": "记",
            "skill_title": "技",
            "skill_body": "- a",
            "principle_title": "无",
            "principle_body": "无",
        },
        "主题",
    )
    assert "未入库" in md
    assert "确认入库" in md
