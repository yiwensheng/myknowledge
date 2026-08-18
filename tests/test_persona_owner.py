"""Tests for persona owner profile integration."""

from __future__ import annotations

from lib.persona_config import (
    expand_queries_for_owner,
    owner_profile_configured,
    query_refers_to_owner,
    render_owner_context,
)


def test_query_refers_to_owner_pronoun() -> None:
    owner = {"real_name": "易文胜", "nickname": "文胜", "aliases": ""}
    assert query_refers_to_owner("我后续如何发展？", owner)
    assert query_refers_to_owner("文胜的工作记录", owner)


def test_expand_queries_for_owner() -> None:
    owner = {"real_name": "易文胜", "nickname": "文胜", "aliases": "易老师"}
    extras = expand_queries_for_owner("我的工作重点是什么", owner)
    assert "易文胜" in extras
    assert "闪念" in extras


def test_render_owner_context_includes_rules() -> None:
    text = render_owner_context({"real_name": "张三", "nickname": "", "aliases": ""})
    assert "知识库主人" in text
    assert "张三" in text
    assert "闪念" in text


def test_owner_profile_configured() -> None:
    assert owner_profile_configured({"real_name": "A", "nickname": ""})
    assert not owner_profile_configured({"real_name": "", "nickname": ""})
