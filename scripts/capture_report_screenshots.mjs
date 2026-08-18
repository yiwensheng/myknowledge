/**
 * Capture Myknowledge GUI screenshots for project report.
 * Prerequisite: backend running (python -m backend).
 *
 * Usage:
 *   cd e:\app\Myknowledge
 *   npx playwright install chromium
 *   node scripts/capture_report_screenshots.mjs
 */
import { chromium } from "playwright";
import { mkdir } from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(ROOT, "docs", "report-screenshots");
const INDEX = path.join(ROOT, "electron", "renderer", "index.html");
const API = process.env.MYKNOWLEDGE_API || "http://127.0.0.1:18765";

const TABS = [
  ["ask", "01-tab-ask"],
  ["query", "02-tab-query"],
  ["list", "03-tab-notes"],
  ["produce", "04-tab-produce"],
  ["manage", "05-tab-import"],
  ["library", "06-tab-library"],
  ["history", "07-tab-history"],
];

async function waitBackend(page) {
  for (let i = 0; i < 30; i++) {
    try {
      const res = await page.request.get(`${API}/api/health`);
      if (res.ok()) return;
    } catch {
      /* retry */
    }
    await page.waitForTimeout(500);
  }
  throw new Error(`Backend not reachable at ${API}`);
}

async function shot(page, name) {
  const file = path.join(OUT, `${name}.png`);
  await page.screenshot({ path: file, fullPage: false });
  console.log("saved", file);
}

async function main() {
  await mkdir(OUT, { recursive: true });

  const browser = await chromium.launch({
    headless: true,
    args: ["--disable-web-security", "--allow-file-access-from-files"],
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    colorScheme: "light",
  });
  await context.addInitScript((apiBase) => {
    window.myknowledge = {
      apiBase,
      deviceId: "report-screenshot",
      ensureFileViewer: async () => {},
      openAssetViewer: async () => {},
      pickDirectory: async () => null,
    };
  }, API);

  const page = await context.newPage();
  await waitBackend(page);

  const indexUrl = `file:///${INDEX.replace(/\\/g, "/")}`;
  await page.goto(indexUrl, { waitUntil: "networkidle", timeout: 60000 });
  await page.waitForSelector(".tab.active", { timeout: 15000 });
  await page.waitForTimeout(1200);

  await shot(page, "00-main-ask");

  for (const [tab, name] of TABS) {
    await page.click(`.tab[data-tab="${tab}"]`);
    await page.waitForSelector(`#panel-${tab}.active`, { timeout: 10000 });
    await page.waitForTimeout(800);
    if (tab === "library") {
      await page.waitForTimeout(1200);
    }
    await shot(page, name);
  }

  await page.click("#btn-settings");
  await page.waitForSelector("#settings-modal:not(.hidden)", { timeout: 10000 });
  await page.waitForTimeout(600);
  await shot(page, "08-modal-settings");

  await page.click("#btn-settings-cancel");
  await page.waitForTimeout(500);

  await page.click("#btn-persona");
  await page.waitForSelector("#persona-modal:not(.hidden)", { timeout: 10000 });
  await page.waitForTimeout(600);
  await shot(page, "09-modal-persona");

  await page.click("#btn-persona-cancel");
  await page.waitForSelector("#persona-modal.hidden", { timeout: 5000 });

  await browser.close();
  console.log("Done. Output:", OUT);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
