"""Unit tests for Bilibili subtitle ingest helpers."""

from __future__ import annotations

import pytest

from lib.bilibili_fetch import (
    _NO_SUB_MSG,
    build_bilibili_markdown,
    is_bilibili_url,
    pick_subtitle_lang,
    vtt_to_text,
)


@pytest.mark.parametrize(
    "url,ok",
    [
        ("https://www.bilibili.com/video/BV1xx411c7mD", True),
        ("https://bilibili.com/video/av2", True),
        ("https://b23.tv/abcdef", True),
        ("https://www.b23.tv/xyz", True),
        ("https://www.toutiao.com/article/1", False),
        ("https://mp.weixin.qq.com/s/abc", False),
    ],
)
def test_is_bilibili_url(url: str, ok: bool) -> None:
    assert is_bilibili_url(url) is ok


def test_pick_subtitle_lang_prefers_zh_hans() -> None:
    available = {
        "en": [{"ext": "vtt"}],
        "zh-Hans": [{"ext": "vtt"}],
        "ai-zh": [{"ext": "vtt"}],
    }
    assert pick_subtitle_lang(available) == "zh-Hans"


def test_pick_subtitle_lang_falls_back_ai_zh() -> None:
    available = {"en": [{"ext": "vtt"}], "ai-zh": [{"ext": "vtt"}]}
    assert pick_subtitle_lang(available) == "ai-zh"


def test_pick_subtitle_lang_empty() -> None:
    assert pick_subtitle_lang({}) is None


def test_vtt_to_text_strips_timestamps() -> None:
    vtt = """WEBVTT

00:00:01.000 --> 00:00:03.000
第一句

00:00:03.000 --> 00:00:05.000
第一句

00:00:05.000 --> 00:00:07.000
第二句讲解
"""
    text = vtt_to_text(vtt)
    assert "第一句" in text
    assert "第二句讲解" in text
    assert "-->" not in text
    # consecutive duplicate removed once
    assert text.count("第一句") == 1


def test_build_markdown_contains_sections() -> None:
    md = build_bilibili_markdown(
        title="测试视频",
        uploader="UP主甲",
        url="https://www.bilibili.com/video/BV1",
        lang="zh-Hans",
        body="正文内容足够长用于入库测试。",
        video_id="BV1",
    )
    assert md.startswith("# 测试视频")
    assert "UP主甲" in md
    assert "字幕文稿" in md
    assert "正文内容足够长用于入库测试。" in md


def test_no_sub_message_constant() -> None:
    assert "无可用字幕" in _NO_SUB_MSG
