#!/usr/bin/env python3
"""Automated acceptance tests for 易知四期改进方案。退出码 0 = 全部通过。"""

from __future__ import annotations

import importlib
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RENDERER = ROOT / "electron" / "renderer"
FAILURES: list[str] = []


def ok(name: str) -> None:
    print(f"  PASS  {name}")


def fail(name: str, detail: str) -> None:
    print(f"  FAIL  {name}: {detail}")
    FAILURES.append(f"{name}: {detail}")


def check(cond: bool, name: str, detail: str = "") -> None:
    if cond:
        ok(name)
    else:
        fail(name, detail or "assertion failed")


def phase1_ui_files() -> None:
    print("\n=== Phase 1: UI / 任务反馈 ===")
    for rel in ("toast.js", "confirm.js", "jobs-ui.js"):
        check((RENDERER / rel).is_file(), f"file {rel}")
    html = (RENDERER / "index.html").read_text(encoding="utf-8")
    for el in (
        "task-center-wrap",
        "btn-task-center",
        "global-job-panel",
        "reconnect-banner",
        "toast-stack",
        "data-busy-scope",
    ):
        check(el in html, f"index.html contains {el}")
    jobs = (RENDERER / "jobs-ui.js").read_text(encoding="utf-8")
    check("startPolling" in jobs and "/api/upload/jobs/active" in jobs, "jobs-ui polls upload")
    check("YizhiToast" in (RENDERER / "toast.js").read_text(encoding="utf-8"), "toast module")


def phase2_index_backend() -> None:
    print("\n=== Phase 2: 索引 / 性能 ===")
    from lib import index_writer, index_jobs, rag, watcher

    check(hasattr(index_writer, "with_index_lock"), "index_writer.with_index_lock")
    check(hasattr(index_writer, "schedule_debounced_sync"), "index_writer.debounce")
    check(hasattr(index_writer, "schedule_index_build"), "index_writer.lazy build")

    src = Path(watcher.__file__).read_text(encoding="utf-8")
    check("defer_index=True" in src, "watcher defer_index")
    check("schedule_debounced_sync" in src, "watcher debounced sync")

    rag_src = Path(rag.__file__).read_text(encoding="utf-8")
    check("_load_index_lazy" in rag_src, "rag lazy load")
    check("is_index_building" in rag_src, "rag status index_building")

    st = rag.rag_status()
    check("index_building" in st, "rag_status.index_building")
    emb = st.get("embeddings") or {}
    check("completeness_pct" in emb, "embedding completeness_pct")

    info = index_jobs.start_index_job()
    check(info.get("job_id"), "index job starts")
    time.sleep(0.5)
    active = index_jobs.list_active_jobs()
    check(any(j.get("id") == info.get("job_id") for j in active) or info.get("already_running"), "index job active")

    # lazy index: empty wiki temp dir should not block
    with tempfile.TemporaryDirectory() as tmp:
        w = Path(tmp)
        (w / ".rag").mkdir(parents=True, exist_ok=True)
        chunks, df = rag._load_index_lazy(w)
        check(chunks == [] and df == {}, "lazy index returns empty without sync block")


def phase3_features() -> None:
    print("\n=== Phase 3: 功能补齐 ===")
    from lib.url_fetch import _clean_weixin_content, _fetch_weixin, _is_weixin_url
    from lib.url_ingest import validate_url_page_quality
    from lib.capabilities import list_capabilities
    from lib.maintenance import list_draft_summary, list_external_rag_chunks

    check(_is_weixin_url("https://mp.weixin.qq.com/s/abc"), "weixin url detect")
    title, body = _clean_weixin_content("# 真实标题\n\n正文内容足够长" + "x" * 100, "mp.weixin.qq.com")
    check(title == "真实标题", "weixin title cleanup", f"got {title!r}")

    class FakePage:
        title = "mp.weixin.qq.com"
        markdown = "微信扫一扫\n" * 3

    q = validate_url_page_quality(FakePage())
    check(q.get("quality_ok") is False, "shell page quality detect")

    caps = list_capabilities()
    check(len(caps.get("items") or []) >= 4, "capabilities list")

    drafts = list_draft_summary(limit=5)
    check("draft_total" in drafts, "draft summary API shape")

    from lib.maintenance import mark_pages_refined

    bad = mark_pages_refined(["../etc/passwd", "nonexistent-page.md"])
    check(bad["refined_count"] == 0 and len(bad["errors"]) == 2, "refine rejects bad paths")

    ext = list_external_rag_chunks(page=1, size=5)
    check("items" in ext, "external chunks API shape")

    server = (ROOT / "backend" / "server.py").read_text(encoding="utf-8")
    for route in (
        "/api/capabilities",
        "/api/maintenance/drafts",
        "/api/maintenance/refine",
        "/api/library/external",
        "/api/index/jobs/active",
    ):
        check(route in server, f"route {route}")


def phase4_productize() -> None:
    print("\n=== Phase 4: 产品化 ===")
    html = (RENDERER / "index.html").read_text(encoding="utf-8")
    check('role="tablist"' in html, "tab tablist a11y")
    check("confirm-modal" in html, "confirm modal in DOM")

    onboarding = (RENDERER / "onboarding.js").read_text(encoding="utf-8")
    check("onboarding-backdrop" in onboarding and "data-onboarding-skip" not in onboarding.split("backdrop")[1][:80], "onboarding backdrop no skip")

    cli = (ROOT / "lib" / "cli.py").read_text(encoding="utf-8")
    check("--async" in cli and "cmd_jobs" in cli, "cli async url + jobs")

    from lib.rag_fts_eval import fts5_recommendation

    low = fts5_recommendation(100)
    high = fts5_recommendation(25_000)
    check(low.get("fts5_recommended") is False, "fts5 not needed below threshold")
    check(high.get("fts5_recommended") is True, "fts5 recommended above threshold")

    st = importlib.import_module("lib.rag").rag_status()
    check("fts5_recommended" in st, "rag_status includes fts5 eval")

    app = (RENDERER / "app.js").read_text(encoding="utf-8")
    alert_count = app.count("alert(")
    confirm_count = app.count("confirm(")
    check(alert_count < 25, f"alert count reduced ({alert_count} < 25)", f"still {alert_count}")
    check("YizhiToast" in app, "app uses YizhiToast")
    check("keydown" in app and "ArrowRight" in app, "tab keyboard nav")


def main() -> int:
    print("易知改进方案 — 四期自动验收")
    phase1_ui_files()
    phase2_index_backend()
    phase3_features()
    phase4_productize()
    print("\n" + "=" * 40)
    if FAILURES:
        print(f"FAILED: {len(FAILURES)}")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("ALL PHASES PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
