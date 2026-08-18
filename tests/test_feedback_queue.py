"""Feedback queue helpers (no network)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from lib.feedback import enqueue_feedback, pending_count, _queue_dir


def test_enqueue_keeps_file_when_post_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WIKI_ROOT", str(tmp_path))
    monkeypatch.setenv("MYKNOWLEDGE_ROOT", str(tmp_path))

    def boom(_item):
        raise RuntimeError("网络不可用: offline")

    with patch("lib.feedback._post_remote", side_effect=boom):
        with patch("lib.feedback.compute_device_id", return_value="device-test-12345678"):
            out = enqueue_feedback(html="<p>测试反馈内容足够长</p>", subject="测", contact="")
    assert out["queued"] is True
    assert out["sent"] is False
    assert pending_count() >= 1
    files = list(_queue_dir().glob("*.json"))
    assert files
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert "测试反馈" in data["html"]


def test_enqueue_clears_file_when_server_accepts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WIKI_ROOT", str(tmp_path))
    monkeypatch.setenv("MYKNOWLEDGE_ROOT", str(tmp_path))

    def ok(_item):
        return {"ok": True, "stored": True, "mailed": True, "method": "smtp"}

    with patch("lib.feedback._post_remote", side_effect=ok):
        with patch("lib.feedback.compute_device_id", return_value="device-test-12345678"):
            out = enqueue_feedback(html="<p>测试反馈内容足够长</p>", subject="测", contact="")
    assert out["sent"] is True
    assert out["mailed"] is True
    assert pending_count() == 0
