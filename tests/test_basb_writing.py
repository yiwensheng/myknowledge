"""Smoke tests for BASB injection into produce system prompt."""

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


def test_basb_block_when_enabled(monkeypatch):
    monkeypatch.setenv("MYKNOWLEDGE_BASB", "1")
    from lib.basb_writing import get_basb_block

    block = get_basb_block()
    assert "思想群岛" in block
    assert "中间成果包" in block or "中间" in block


def test_basb_block_when_disabled(monkeypatch):
    monkeypatch.setenv("MYKNOWLEDGE_BASB", "0")
    from lib.basb_writing import get_basb_block

    assert get_basb_block() == ""


def test_produce_includes_basb_when_on(monkeypatch):
    monkeypatch.setenv("MYKNOWLEDGE_BASB", "1")
    from lib.prompts import system_for_produce

    assert "思想群岛" in system_for_produce()


def test_produce_omits_basb_when_off(monkeypatch):
    monkeypatch.setenv("MYKNOWLEDGE_BASB", "0")
    from lib.prompts import system_for_produce

    # yizhi-rules title marker
    assert "BASB 写作与知识复用" not in system_for_produce()
