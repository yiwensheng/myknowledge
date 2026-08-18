"""Tests for produce revise prompt + finalize."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lib.llm import _build_revise_prompt, finalize_produce


def test_revise_prompt_without_rag_includes_draft_and_instruction() -> None:
    prompt, chunks, g = _build_revise_prompt(
        content="# 旧稿\n\n第一段。",
        instruction="把语气改得更正式",
        topic="教学质量",
        genre="article",
        use_rag=False,
    )
    assert chunks == []
    assert "改稿要求" in prompt
    assert "把语气改得更正式" in prompt
    assert "旧稿" in prompt or "第一段" in prompt
    assert "参考检索片段" not in prompt
    assert g["id"] == "article"


def test_revise_prompt_with_rag_includes_context() -> None:
    fake_chunk = MagicMock()
    fake_chunk.title = "t"
    fake_chunk.rel_path = "notes/a.md"
    fake_chunk.score = 1.0
    fake_chunk.retrieval = "kw"
    fake_chunk.text = "片段正文"
    fake_chunk.asset_path = ""
    fake_chunk.tags = []

    with patch("lib.llm.search", return_value=[fake_chunk]):
        with patch("lib.llm.format_context", return_value="【1】片段正文"):
            prompt, chunks, g = _build_revise_prompt(
                content="正文",
                instruction="补充数据",
                topic="教学质量",
                genre="article",
                use_rag=True,
            )
    assert len(chunks) == 1
    assert "参考检索片段" in prompt
    assert "补充数据" in prompt


def test_finalize_produce_saves_with_rel_path() -> None:
    page = MagicMock()
    page.rel_path = "notes/old.md"
    with patch("lib.llm.save_page", return_value=page) as sp:
        with patch("lib.ingest.defer_refresh_rag"):
            out = finalize_produce(
                content="# 标题\n\n足够长的正文用于定稿测试内容。",
                topic="主题",
                genre="article",
                wiki_page="notes/old.md",
            )
    assert out["wiki_page"] == "notes/old.md"
    assert sp.call_args.kwargs.get("rel_path") == "notes/old.md"
    assert sp.call_args.kwargs.get("status") == "draft"


def test_finalize_rejects_empty() -> None:
    with pytest.raises(ValueError, match="空"):
        finalize_produce(content="  ", topic="t", genre="article")
