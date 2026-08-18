"""Smoke tests for de-AI writing bundle injection."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_prompt_caches():
    from lib import prompts

    for fn in (prompts.system_for_ask, prompts.system_for_produce, prompts.system_for_deduce):
        if hasattr(fn, "_cache"):
            delattr(fn, "_cache")
    yield
    for fn in (prompts.system_for_ask, prompts.system_for_produce, prompts.system_for_deduce):
        if hasattr(fn, "_cache"):
            delattr(fn, "_cache")


def test_de_ai_block_when_enabled(monkeypatch):
    monkeypatch.setenv("MYKNOWLEDGE_DE_AI_WRITING", "1")
    from lib.de_ai_writing import get_de_ai_writing_block

    block = get_de_ai_writing_block()
    assert "讲义" in block or "路标" in block
    assert "Humanizer" in block or "说人话" in block


def test_de_ai_block_when_disabled(monkeypatch):
    monkeypatch.setenv("MYKNOWLEDGE_DE_AI_WRITING", "0")
    from lib.de_ai_writing import get_de_ai_writing_block

    assert get_de_ai_writing_block() == ""


def test_produce_includes_de_ai_when_on(monkeypatch):
    monkeypatch.setenv("MYKNOWLEDGE_DE_AI_WRITING", "1")
    from lib.prompts import system_for_produce

    assert "去 AI 味增强" in system_for_produce()


def test_produce_omits_de_ai_when_off(monkeypatch):
    monkeypatch.setenv("MYKNOWLEDGE_DE_AI_WRITING", "0")
    from lib.prompts import system_for_produce

    assert "去 AI 味增强" not in system_for_produce()
