/**
 * 易知宣传录屏：用 Playwright 启动 Electron，点选主功能后写出视频。
 *
 * 用法（在本目录）：
 *   npm install
 *   npm run record
 *
 * 可选环境变量：
 *   PROMO_THEME=light|dark    界面主题，默认 light
 *   PROMO_OUT=E:\\videos      输出目录，默认 Myknowledge/dist/promo-videos
 *   PROMO_DWELL_MS=900        每步停留毫秒
 *   PROMO_SKIP_AUDIO=1        不播放「自我介绍」音频
 *   PROMO_WIDTH=1280
 *   PROMO_HEIGHT=800
 *
 * 注意：lib/config.load_dotenv 会用仓库 .env 覆盖 MYKNOWLEDGE_*，
 * 故后台端口固定跟 .env 的 MYKNOWLEDGE_PORT（默认 18765）。录屏前请先关掉已开的易知。
 *
 * 产出：*.webm（Chromium 录屏）；若本机有 ffmpeg 会再转一份 mp4。
 */

const { _electron: electron } = require("playwright");
const path = require("path");
const fs = require("fs");
const http = require("http");
const { spawn, spawnSync } = require("child_process");

const ROOT = path.resolve(__dirname, "../..");
const ELECTRON_DIR = path.join(ROOT, "electron");
const DWELL = Math.max(400, Number(process.env.PROMO_DWELL_MS || 900));
const WIDTH = Number(process.env.PROMO_WIDTH || 1280);
const HEIGHT = Number(process.env.PROMO_HEIGHT || 800);
const THEME = (process.env.PROMO_THEME || "light").toLowerCase() === "dark" ? "dark" : "light";
/** 与仓库 .env 一致；MYKNOWLEDGE_PORT 会被 dotenv 强制成 .env 值 */
function readPortFromDotenv() {
  try {
    const text = fs.readFileSync(path.join(ROOT, ".env"), "utf8");
    const m = text.match(/^\s*MYKNOWLEDGE_PORT\s*=\s*(\d+)/m);
    if (m) return m[1];
  } catch {
    /* ignore */
  }
  return "18765";
}
const PORT = readPortFromDotenv();
const DOCUBROWSER_PORT = "18766";
const OUT_DIR = path.resolve(process.env.PROMO_OUT || path.join(ROOT, "dist", "promo-videos"));
const SKIP_AUDIO = process.env.PROMO_SKIP_AUDIO === "1";

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function stamp() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

function resolveElectronExe() {
  const fromEnv = (process.env.ELECTRON_PATH || "").trim();
  if (fromEnv && fs.existsSync(fromEnv)) return fromEnv;
  // eslint-disable-next-line import/no-dynamic-require, global-require
  const electronPath = require(path.join(ELECTRON_DIR, "node_modules", "electron"));
  if (typeof electronPath === "string" && fs.existsSync(electronPath)) return electronPath;
  throw new Error("找不到 electron 可执行文件，请先在 electron/ 下 npm install");
}

function cleanEnv(extra = {}) {
  const out = {};
  for (const [k, v] of Object.entries({ ...process.env, ...extra })) {
    if (v === undefined || v === null) continue;
    out[k] = String(v);
  }
  return out;
}

function fetchHealth(port, timeoutMs = 2500) {
  return new Promise((resolve) => {
    const req = http.get(
      {
        hostname: "127.0.0.1",
        port: Number(port),
        path: "/api/health",
        timeout: timeoutMs,
      },
      (res) => {
        let body = "";
        res.on("data", (c) => {
          body += c;
        });
        res.on("end", () => {
          try {
            resolve(JSON.parse(body));
          } catch {
            resolve(null);
          }
        });
      }
    );
    req.on("error", () => resolve(null));
    req.on("timeout", () => {
      req.destroy();
      resolve(null);
    });
  });
}

async function waitHealth(port, timeoutMs = 180000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const h = await fetchHealth(port);
    if (h?.ok && Array.isArray(h.capabilities) && h.capabilities.includes("ask_stream")) {
      return h;
    }
    await sleep(800);
  }
  throw new Error(`后台未在 ${timeoutMs}ms 内就绪（端口 ${port}）`);
}

function killPortWindows(port) {
  if (process.platform !== "win32") return;
  try {
    const out =
      spawnSync("netstat", ["-ano", "-p", "tcp"], {
        encoding: "utf8",
        windowsHide: true,
        timeout: 8000,
      }).stdout || "";
    const pids = new Set();
    const re = new RegExp(`:${port}\\s+\\S+\\s+LISTENING\\s+(\\d+)`, "i");
    for (const line of out.split(/\r?\n/)) {
      const m = line.match(re);
      if (m) pids.add(m[1]);
    }
    for (const pid of pids) {
      if (!pid || pid === "0") continue;
      console.log(`[promo] 释放端口 ${port}，结束 PID ${pid}`);
      spawnSync("taskkill", ["/F", "/PID", pid], { windowsHide: true, stdio: "ignore" });
    }
  } catch {
    /* ignore */
  }
}

/**
 * Electron 冷启动时 backend 常超过其内置等待；宣传录屏先起后台，再开窗口。
 * @returns {{ proc: import('child_process').ChildProcess|null, owned: boolean }}
 */
async function ensureBackend() {
  const existing = await fetchHealth(PORT);
  if (existing?.ok && existing.capabilities?.includes("ask_stream")) {
    console.log(`[promo] 复用已运行后台 :${PORT}`);
    return { proc: null, owned: false };
  }
  killPortWindows(PORT);
  await sleep(600);
  console.log(`[promo] 预启动后台 python -m backend :${PORT} …`);
  const proc = spawn("python", ["-m", "backend"], {
    cwd: ROOT,
    env: cleanEnv({
      YIZHI_DEV: "1",
      WIKI_ROOT: ROOT,
      MYKNOWLEDGE_ROOT: ROOT,
      PYTHONIOENCODING: "utf-8",
    }),
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  const logPath = path.join(OUT_DIR, `backend-promo-${PORT}.log`);
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const logStream = fs.createWriteStream(logPath, { flags: "a" });
  proc.stdout?.pipe(logStream);
  proc.stderr?.pipe(logStream);
  try {
    await waitHealth(PORT, 180000);
    console.log(`[promo] 后台就绪 :${PORT}`);
    return { proc, owned: true };
  } catch (e) {
    try {
      proc.kill();
    } catch {
      /* ignore */
    }
    throw e;
  }
}

async function waitMainWindow(app, timeoutMs = 180000) {
  const deadline = Date.now() + timeoutMs;
  let lastDump = "";
  while (Date.now() < deadline) {
    const windows = app.windows();
    const dump = [];
    for (const w of windows) {
      let url = "";
      let title = "";
      try {
        url = w.url();
        title = await w.title().catch(() => "");
      } catch {
        continue;
      }
      dump.push(`${title || "?"} :: ${url}`);
      // 主界面（排除 splash / viewer）
      if (
        (url.includes("index.html") || /[/\\]renderer[/\\]index\.html/i.test(url)) &&
        !url.includes("splash")
      ) {
        await w.waitForLoadState("domcontentloaded").catch(() => {});
        // 等品牌与 Tab 出现
        await w.locator(".tab[data-tab='ask'], #ask-input, header.header").first().waitFor({
          state: "visible",
          timeout: 30000,
        }).catch(() => {});
        return w;
      }
    }
    const joined = dump.join(" | ");
    if (joined && joined !== lastDump) {
      console.log(`[promo] 窗口: ${joined || "(无)"}`);
      lastDump = joined;
    }
    await sleep(500);
  }
  throw new Error(
    "超时：未等到易知主窗口。请确认开发环境能 `cd electron && npm start`，且 PROMO_PORT 未被占用（勿用 18765/18766）。"
  );
}

async function safeClick(page, selector, opts = {}) {
  const loc = page.locator(selector).first();
  const visible = await loc.isVisible().catch(() => false);
  if (!visible) return false;
  await loc.click({ timeout: opts.timeout || 8000, ...opts }).catch(() => {});
  await sleep(opts.dwell ?? DWELL);
  return true;
}

async function dismissChrome(page) {
  // 新手指引
  if (await page.locator("[data-onboarding-skip]").isVisible().catch(() => false)) {
    await page.locator("[data-onboarding-skip]").click().catch(() => {});
    await sleep(400);
  }
  // 授权遮罩（试用关闭钮；强制锁定时可能关不掉）
  const licClose = page.locator("#btn-license-close");
  if (await licClose.isVisible().catch(() => false)) {
    await licClose.click().catch(() => {});
    await sleep(300);
  }
  // 残留弹窗
  for (const sel of ["#about-close", "#feedback-cancel", "#btn-persona-cancel", "#btn-settings-cancel"]) {
    const el = page.locator(sel);
    if (await el.isVisible().catch(() => false)) {
      await el.click().catch(() => {});
      await sleep(200);
    }
  }
}

async function waitBackendReady(page, timeoutMs = 90000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const text = ((await page.locator("#status").textContent().catch(() => "")) || "").trim();
    if (text && !/正在连接|连接中|启动/.test(text)) return text;
    const reconnect = await page.locator("#reconnect-banner:not(.hidden)").isVisible().catch(() => false);
    if (reconnect) {
      await safeClick(page, "#btn-reconnect", { dwell: 1500 });
    }
    await sleep(500);
  }
  console.warn("[promo] 警告：状态栏仍像未连上后台，继续录屏（部分面板可能为空）");
}

async function clickTabs(page, selectorList) {
  for (const sel of selectorList) {
    await safeClick(page, sel);
  }
}

async function runTour(page) {
  await page.evaluate(
    ({ theme }) => {
      try {
        localStorage.setItem("myk-onboarding-v2", "1");
        localStorage.setItem("myk-theme", theme);
        document.documentElement.setAttribute("data-theme", theme);
      } catch {
        /* ignore */
      }
    },
    { theme: THEME }
  );
  await dismissChrome(page);
  await waitBackendReady(page);

  // 主题
  await safeClick(page, `.theme-btn[data-theme="${THEME}"]`);

  // —— 顶栏 ——
  console.log("[promo] 人设");
  await safeClick(page, "#btn-persona", { dwell: DWELL + 200 });
  await clickTabs(page, [
    '#persona-tabs .modal-tab[data-persona-tab="profile"]',
    '#persona-tabs .modal-tab[data-persona-tab="role"]',
    '#persona-tabs .modal-tab[data-persona-tab="style"]',
    '#persona-tabs .modal-tab[data-persona-tab="preview"]',
  ]);
  await safeClick(page, "#btn-persona-cancel");

  console.log("[promo] 设置");
  await safeClick(page, "#btn-settings", { dwell: DWELL + 300 });
  const settingTabs = page.locator("#settings-form .modal-tab[data-tab]");
  const nSettings = await settingTabs.count().catch(() => 0);
  for (let i = 0; i < nSettings; i++) {
    await settingTabs.nth(i).click().catch(() => {});
    await sleep(DWELL);
  }
  await safeClick(page, "#btn-settings-cancel");

  console.log("[promo] 关于");
  await safeClick(page, "#btn-about", { dwell: DWELL + 400 });
  if (!SKIP_AUDIO) {
    await safeClick(page, "#btn-about-promo-audio", { dwell: 2800 });
    // 停播，避免拖太长
    await page
      .evaluate(() => {
        const a = document.getElementById("about-self-intro-audio");
        if (a instanceof HTMLAudioElement) {
          a.pause();
          a.currentTime = 0;
        }
      })
      .catch(() => {});
  }
  await safeClick(page, "#about-close");

  console.log("[promo] 反馈");
  await safeClick(page, "#btn-feedback", { dwell: DWELL + 500 });
  await safeClick(page, "#feedback-cancel");

  // —— 主 Tab ——
  const mainTabs = [
    ["ask", "提问"],
    ["query", "查询"],
    ["deduce", "推演"],
    ["list", "笔记"],
    ["produce", "写文章"],
    ["manage", "导入资料"],
    ["library", "资料库"],
    ["history", "历史"],
  ];

  for (const [id, label] of mainTabs) {
    console.log(`[promo] Tab · ${label}`);
    await safeClick(page, `.tab[data-tab="${id}"]`, { dwell: DWELL + 200 });

    if (id === "ask") {
      await page.locator("#ask-input").fill("易知能帮我做什么？用三句话概括。").catch(() => {});
      await sleep(DWELL);
    }
    if (id === "query") {
      await page.locator("#query-input").fill("知识库").catch(() => {});
      await sleep(DWELL * 0.6);
    }
    if (id === "deduce") {
      await page.locator("#deduce-input").fill("我的工作与学习主题之间有什么关联？").catch(() => {});
      await sleep(DWELL);
    }
    if (id === "list") {
      await safeClick(page, '.notes-view-btn[data-notes-view="timeline"]');
      await safeClick(page, '.notes-view-btn[data-notes-view="editor"]');
      await safeClick(page, '.notes-view-btn[data-notes-view="timeline"]');
    }
    if (id === "produce") {
      await page.locator("#produce-input").fill("用易知做个人知识管理的三个实践建议").catch(() => {});
      await sleep(DWELL);
    }
    if (id === "manage") {
      await clickTabs(page, [
        '.manage-tab[data-manage-view="import"]',
        '.manage-tab[data-manage-view="drafts"]',
        '.manage-tab[data-manage-view="linked"]',
        '.manage-tab[data-manage-view="assets"]',
        '.manage-tab[data-manage-view="import"]',
      ]);
    }
    if (id === "library") {
      await clickTabs(page, [
        '.lib-tab[data-lib="assets"]',
        '.lib-tab[data-lib="rag"]',
        '.lib-tab[data-lib="external"]',
        '.lib-tab[data-lib="assets"]',
      ]);
      await safeClick(page, "#btn-library-refresh", { dwell: DWELL });
    }
    if (id === "history") {
      await safeClick(page, "#btn-history-refresh", { dwell: DWELL });
    }
  }

  // 回到提问收尾
  console.log("[promo] 收尾 · 提问");
  await safeClick(page, '.tab[data-tab="ask"]', { dwell: DWELL + 600 });
  await sleep(1200);
}

function tryConvertMp4(webmPath) {
  const mp4Path = webmPath.replace(/\.webm$/i, ".mp4");
  const ffmpegCandidates = [
    process.env.FFMPEG_PATH,
    path.join(ROOT, "third_party", "ffmpeg", "ffmpeg.exe"),
    "ffmpeg",
  ].filter(Boolean);
  for (const bin of ffmpegCandidates) {
    const r = spawnSync(
      bin,
      ["-y", "-i", webmPath, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", mp4Path],
      { encoding: "utf8" }
    );
    if (r.status === 0 && fs.existsSync(mp4Path)) {
      console.log(`[promo] 已转码 MP4 → ${mp4Path}`);
      return mp4Path;
    }
  }
  console.log("[promo] 未找到可用 ffmpeg，保留 webm（可自行转 mp4）");
  return null;
}

async function main() {
  if (!fs.existsSync(path.join(ELECTRON_DIR, "main.js"))) {
    throw new Error(`未找到 ${ELECTRON_DIR}\\main.js`);
  }
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const runId = stamp();
  const sessionDir = path.join(OUT_DIR, `session-${runId}`);
  fs.mkdirSync(sessionDir, { recursive: true });

  const electronExe = resolveElectronExe();
  console.log(`[promo] electron = ${electronExe}`);
  console.log(`[promo] port = ${PORT} (docubrowser=${DOCUBROWSER_PORT})`);
  console.log(`[promo] theme = ${THEME}`);
  console.log(`[promo] video dir = ${sessionDir}`);

  const backend = await ensureBackend();
  let app;
  let page;
  try {
    app = await electron.launch({
      executablePath: electronExe,
      args: [ELECTRON_DIR],
      cwd: ELECTRON_DIR,
      env: cleanEnv({
        YIZHI_DEV: "1",
        // 与 .env 一致，避免 Electron 探活端口和 Python dotenv 覆盖后不一致
        MYKNOWLEDGE_PORT: PORT,
        MYKKNOWLEDGE_DOCUBROWSER_PORT: DOCUBROWSER_PORT,
        WIKI_ROOT: ROOT,
        MYKNOWLEDGE_ROOT: ROOT,
        ELECTRON_DISABLE_SECURITY_WARNINGS: "1",
      }),
      timeout: 180000,
      recordVideo: {
        dir: sessionDir,
        size: { width: WIDTH, height: HEIGHT },
      },
    });

    page = await waitMainWindow(app);
    await app.evaluate(
      ({ BrowserWindow }, size) => {
        const wins = BrowserWindow.getAllWindows().filter((w) => !w.isDestroyed());
        const main = wins.find((w) => {
          try {
            return (w.getTitle() || "").includes("易知") && w.getSize()[0] >= 800;
          } catch {
            return false;
          }
        });
        const target = main || wins[wins.length - 1];
        if (target) {
          target.setSize(size.width, size.height);
          target.center();
          target.show();
          target.focus();
        }
      },
      { width: WIDTH, height: HEIGHT }
    );
    await sleep(800);
    await runTour(page);
  } finally {
    const video = page ? page.video() : null;
    if (app) await app.close().catch(() => {});
    if (backend.owned && backend.proc && !backend.proc.killed) {
      try {
        backend.proc.kill();
      } catch {
        /* ignore */
      }
    }
    if (video) {
      const rawPath = await video.path().catch(() => null);
      if (rawPath && fs.existsSync(rawPath)) {
        const destWebm = path.join(OUT_DIR, `yizhi-promo-${runId}.webm`);
        fs.copyFileSync(rawPath, destWebm);
        console.log(`[promo] 视频已生成 → ${destWebm}`);
        tryConvertMp4(destWebm);
        try {
          fs.rmSync(sessionDir, { recursive: true, force: true });
        } catch {
          /* keep */
        }
      } else {
        console.warn("[promo] 未拿到 video.path，请查看目录：", sessionDir);
      }
    }
  }
}

main().catch((err) => {
  console.error("[promo] 失败：", err);
  process.exit(1);
});
