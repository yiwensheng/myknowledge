"""Capture Myknowledge GUI screenshots for project report (Playwright).

Prerequisite: backend running — python -m backend

Usage:
    cd e:\\app\\Myknowledge
    python scripts/capture_report_screenshots.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "report-screenshots"
INDEX = ROOT / "electron" / "renderer" / "index.html"
API = "http://127.0.0.1:18765"

TABS = [
    ("ask", "01-tab-ask"),
    ("query", "02-tab-query"),
    ("list", "03-tab-notes"),
    ("produce", "04-tab-produce"),
    ("manage", "05-tab-import"),
    ("library", "06-tab-library"),
    ("history", "07-tab-history"),
]


def wait_backend(page, timeout_s: float = 20.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            resp = page.request.get(f"{API}/api/health")
            if resp.ok:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"Backend not reachable at {API}")


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        print("Install: pip install playwright && python -m playwright install chromium", file=sys.stderr)
        raise SystemExit(1) from e

    OUT.mkdir(parents=True, exist_ok=True)
    index_url = INDEX.as_uri()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-web-security", "--allow-file-access-from-files"],
        )
        context = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light")
        context.add_init_script(
            f'window.myknowledge = {{ apiBase: "{API}", deviceId: "report", '
            "ensureFileViewer: async () => {}, openAssetViewer: async () => {}, pickDirectory: async () => null };"
        )
        page = context.new_page()
        wait_backend(page)
        page.goto(index_url, wait_until="networkidle", timeout=60000)
        page.wait_for_selector(".tab.active", timeout=15000)
        page.wait_for_timeout(1200)

        def shot(name: str) -> None:
            path = OUT / f"{name}.png"
            page.screenshot(path=str(path), full_page=False)
            print("saved", path)

        shot("00-main-ask")
        for tab, name in TABS:
            page.click(f'.tab[data-tab="{tab}"]')
            page.wait_for_selector(f"#panel-{tab}.active", timeout=10000)
            page.wait_for_timeout(1000 if tab == "library" else 700)
            shot(name)

        page.click("#btn-settings")
        page.wait_for_selector("#settings-modal:not(.hidden)", timeout=10000)
        page.wait_for_timeout(600)
        shot("08-modal-settings")
        page.click("#btn-settings-cancel")
        page.wait_for_timeout(500)

        page.click("#btn-persona")
        page.wait_for_selector("#persona-modal:not(.hidden)", timeout=10000)
        page.wait_for_timeout(600)
        shot("09-modal-persona")

        browser.close()

    print("Done:", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
