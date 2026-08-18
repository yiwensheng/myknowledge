"""Unit tests for parent-child chunking and contrarian collectors."""

from __future__ import annotations

from pathlib import Path

from lib.contrarian import _assumptions_from_body, _parse_conflicts
from lib.rag_chunk import chunk_document_parent_child


def test_parent_child_returns_parent_for_children():
    text = (
        "# 标题\n\n"
        + ("段落甲。" * 40)
        + "\n\n## 第二节\n\n"
        + ("段落乙。" * 40)
    )
    items = chunk_document_parent_child(
        text, title="测", parent_size=400, child_size=160, overlap=40
    )
    assert items
    assert all("text" in x and "parent_text" in x and "parent_id" in x for x in items)
    assert any(len(x["parent_text"]) >= len(x["text"]) for x in items)
    parent_ids = {x["parent_id"] for x in items}
    assert len(parent_ids) >= 1


def test_assumptions_from_body():
    body = "## 分析提炼\n\n### 核心假设\n\n- 假设一成立\n- 假设二成立\n\n### 主题\n\n- x\n"
    assert _assumptions_from_body(body) == ["假设一成立", "假设二成立"]


def test_parse_conflicts_json():
    raw = '{"conflicts":[{"a":"A说","b":"B说","path_a":"a.md","path_b":"b.md","why":"互斥"}]}'
    items = _parse_conflicts(raw)
    assert len(items) == 1
    assert items[0]["a"] == "A说"
