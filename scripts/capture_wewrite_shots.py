"""Capture Yizhi UI shots for WeWrite article; dismiss continuity modal first."""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(r"e:\app\Myknowledge")
SRC = ROOT / "docs" / "report-screenshots"
OUT = Path(r"C:\Users\Administrator\.agents\skills\wewrite\output")
API = "http://127.0.0.1:18765"
INDEX = (ROOT / "electron" / "renderer" / "index.html").as_uri()

COPY = {
    "00-main-ask.png": "yizhi-00-main-ask.png",
    "04-tab-produce.png": "yizhi-04-tab-produce.png",
    "05-tab-import.png": "yizhi-05-tab-import.png",
    "08-modal-settings.png": "yizhi-08-modal-settings.png",
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for a, b in COPY.items():
        src = SRC / a
        if src.is_file():
            shutil.copy2(src, OUT / b)
            print("copied", b)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-web-security", "--allow-file-access-from-files"],
        )
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light")
        ctx.add_init_script(
            f'window.myknowledge = {{ apiBase: "{API}", deviceId: "wewrite", '
            "ensureFileViewer: async () => {}, openAssetViewer: async () => {}, "
            "pickDirectory: async () => null };"
            'localStorage.setItem("myk-onboarding-v2", "1");'
            'localStorage.setItem("myk-theme", "light");'
            'localStorage.setItem("myk-continuity-dismiss-date", '
            'new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Shanghai",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date()));'
        )
        page = ctx.new_page()
        for _ in range(40):
            try:
                if page.request.get(f"{API}/api/health").ok:
                    break
            except Exception:
                pass
            time.sleep(0.5)
        page.goto(INDEX, wait_until="networkidle", timeout=60000)
        page.wait_for_selector(".tab.active", timeout=15000)
        # close continuity if still open
        if page.locator("#continuity-modal:not(.hidden)").count():
            page.locator("#btn-continuity-dismiss-today").click(timeout=3000)
            page.wait_for_timeout(300)
        page.locator("#continuity-modal").evaluate(
            "el => el && el.classList.add('hidden')"
        )
        page.wait_for_timeout(500)

        page.screenshot(path=str(OUT / "yizhi-00-main-ask.png"), full_page=False)
        print("shot yizhi-00-main-ask.png")

        for tab, name in [
            ("produce", "yizhi-04-tab-produce.png"),
            ("manage", "yizhi-05-tab-import.png"),
            ("deduce", "yizhi-deduce.png"),
            ("memory", "yizhi-memory.png"),
        ]:
            page.click(f'.tab[data-tab="{tab}"]', force=True)
            page.wait_for_selector(f"#panel-{tab}.active", timeout=10000)
            page.wait_for_timeout(800)
            page.screenshot(path=str(OUT / name), full_page=False)
            print("shot", name)

        page.click('.tab[data-tab="ask"]', force=True)
        page.wait_for_timeout(400)
        page.click("#btn-settings", force=True)
        page.wait_for_selector("#settings-modal:not(.hidden)", timeout=8000)
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUT / "yizhi-08-modal-settings.png"), full_page=False)
        print("shot yizhi-08-modal-settings.png")
        browser.close()


if __name__ == "__main__":
    main()
