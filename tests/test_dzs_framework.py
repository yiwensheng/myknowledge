"""Smoke tests for DZS injection into ask/produce/deduce system prompts."""

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


def test_dzs_block_when_enabled(monkeypatch):
    monkeypatch.setenv("MYKNOWLEDGE_DZS", "1")
    from lib.dzs_framework import get_dzs_block

    block = get_dzs_block()
    assert "三维压力测试" in block or "压力测试" in block
    assert "提问" in block and "写文章" in block and "推演" in block


def test_dzs_block_when_disabled(monkeypatch):
    monkeypatch.setenv("MYKNOWLEDGE_DZS", "0")
    from lib.dzs_framework import get_dzs_block

    assert get_dzs_block() == ""


def test_systems_include_dzs_when_on(monkeypatch):
    monkeypatch.setenv("MYKNOWLEDGE_DZS", "1")
    from lib.prompts import system_for_ask, system_for_deduce, system_for_produce

    marker = "DZS 认知催化"
    assert marker in system_for_ask()
    assert marker in system_for_produce()
    assert marker in system_for_deduce()


def test_systems_omit_dzs_when_off(monkeypatch):
    monkeypatch.setenv("MYKNOWLEDGE_DZS", "0")
    from lib.prompts import system_for_ask, system_for_deduce, system_for_produce

    marker = "DZS 认知催化"
    assert marker not in system_for_ask()
    assert marker not in system_for_produce()
    assert marker not in system_for_deduce()
