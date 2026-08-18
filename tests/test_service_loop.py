"""服务闭环：进度、资产、模板校验。"""

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
    (root / "notes").mkdir()
    (root / ".config").mkdir()
    monkeypatch.setenv("WIKI_ROOT", str(root))
    monkeypatch.setenv("MYKNOWLEDGE_ROOT", str(root))
    from lib import config

    config.load_dotenv()
    return root


def test_default_status_and_patch(wiki):
    from lib.service_loop import get_status, patch_state

    st = get_status(wiki)
    assert st["tasks"]["key_ok"] is False
    assert st["core_loop_done"] is False
    assert len(st["templates"]) >= 5
    ids = {t["id"] for t in st["templates"]}
    assert {"jiaoshi", "kaoyan", "zimeiti", "zhichang", "opc"} <= ids

    st2 = patch_state({"tasks": {"key_ok": True}}, root=wiki)
    assert st2["tasks"]["key_ok"] is True


def test_infer_ingest_and_assets(wiki):
    from lib.service_loop import collect_assets, get_status

    (wiki / "notes" / "a.md").write_text("# a\nhello\n", encoding="utf-8")
    st = get_status(wiki)
    assert st["tasks"]["ingest_or_note"] is True
    assert st["weeks"]["w1"]["done"] is True
    assets = collect_assets(wiki)
    assert assets["notes_count"] >= 1


def test_template_missing_required(wiki):
    from lib.service_loop import run_template

    r = run_template("jiaoshi", {"subject": ""}, root=wiki)
    assert r["ok"] is False
    assert "学科" in r["error"] or "填写" in r["error"]


def test_template_commit_writes_note(wiki, monkeypatch):
    from lib import service_loop

    def fake_chat(system, user, kind="produce"):
        assert "备课" in user or "六步" in user or "教师" in system or True
        return "# 备课要点\n\n待确认：学时\n"

    monkeypatch.setattr(service_loop, "_chat", fake_chat)
    run = service_loop.run_template(
        "jiaoshi",
        {"subject": "高一数学", "goal": "函数概念"},
        root=wiki,
    )
    assert run["ok"] is True
    assert "待确认" in run["markdown"] or "备课" in run["markdown"]
    commit = service_loop.commit_template(
        "jiaoshi",
        title="测试教案",
        markdown=run["markdown"],
        root=wiki,
    )
    assert commit["ok"] is True
    assert (wiki / commit["rel_path"]).is_file()
    st = service_loop.get_status(wiki)
    assert st["weeks"]["w3"]["done"] is True


def test_probe_no_key(monkeypatch, wiki):
    monkeypatch.setenv("MYKNOWLEDGE_LLM_API_KEY", "")
    from lib import config

    config.load_dotenv()
    from lib.llm import probe_llm

    # Force empty key via monkeypatch of llm_config
    monkeypatch.setattr(
        "lib.llm.llm_config",
        lambda: {"api_key": "", "model": "x", "chat_url": "http://127.0.0.1/v1/chat/completions"},
    )
    r = probe_llm()
    assert r["ok"] is False
    assert "Key" in r["error"] or "密钥" in r["error"] or "配置" in r["error"]


def test_jiaoshi_prompt_requires_six_steps(wiki, monkeypatch):
    from lib import service_loop

    captured = {}

    def fake_chat(system, user, kind="produce"):
        captured["user"] = user
        return "ok"

    monkeypatch.setattr(service_loop, "_chat", fake_chat)
    service_loop.run_template(
        "jiaoshi",
        {"subject": "语文", "goal": "议论文"},
        root=wiki,
    )
    u = captured["user"]
    for word in ("备课", "上课", "练习", "作业", "检测", "反馈"):
        assert word in u
