const { app, BrowserWindow, shell, Menu, ipcMain, dialog, nativeImage } = require("electron");
const { computeDeviceId } = require("./device-id");
const path = require("path");
const fs = require("fs");
const os = require("os");
const { spawn, execSync } = require("child_process");
const http = require("http");

const pkg = require("./package.json");
const MYK_ROOT = path.resolve(__dirname, "..");
const PORT = process.env.MYKNOWLEDGE_PORT || "18765";
const API = `http://127.0.0.1:${PORT}`;

/** 安装目录内置 Python 优先于系统 PATH（客户机常无全局 python） */
function preferBundledPythonPath() {
  const candidates =
    process.platform === "win32"
      ? [path.join(MYK_ROOT, "python"), path.join(MYK_ROOT, "python", "Scripts")]
      : [path.join(MYK_ROOT, "python", "bin")];
  const prefix = candidates.filter((d) => fs.existsSync(d)).join(path.delimiter);
  if (!prefix) return;
  process.env.PATH = `${prefix}${path.delimiter}${process.env.PATH || ""}`;
}
preferBundledPythonPath();

function bootLog(msg) {
  try {
    const dir =
      process.env.LOCALAPPDATA
        ? path.join(process.env.LOCALAPPDATA, "Yizhi")
        : path.join(os.homedir(), "AppData", "Local", "Yizhi");
    fs.mkdirSync(dir, { recursive: true });
    fs.appendFileSync(
      path.join(dir, "electron-boot.log"),
      `${new Date().toISOString()} ${msg}\n`,
      "utf8"
    );
  } catch {
    /* ignore */
  }
  try {
    console.log(`[yizhi-boot] ${msg}`);
  } catch {
    /* ignore */
  }
}
bootLog(`main.js load MYK_ROOT=${MYK_ROOT}`);

/** 有内置 runtime\yizhi-backend.exe 或 python\python.exe 即视为安装/便携包 */
function bundledBackendExe() {
  if (process.platform !== "win32") return "";
  const p = path.join(MYK_ROOT, "runtime", "yizhi-backend.exe");
  return fs.existsSync(p) ? p : "";
}

function hasBundledPythonExe() {
  const candidates =
    process.platform === "win32"
      ? [
          path.join(MYK_ROOT, "python", "python.exe"),
          path.join(MYK_ROOT, "python", "Scripts", "python.exe"),
        ]
      : [
          path.join(MYK_ROOT, "python", "bin", "python3"),
          path.join(MYK_ROOT, "python", "bin", "python"),
        ];
  return candidates.some((p) => fs.existsSync(p));
}

function isInstalledLayout() {
  return process.env.YIZHI_INSTALLED === "1";
}

function isBundledLayout() {
  if (process.env.YIZHI_INSTALLED === "1" || process.env.YIZHI_PORTABLE === "1") return true;
  if (process.env.YIZHI_DEV === "1") return false;
  return (
    !!bundledBackendExe() ||
    fs.existsSync(path.join(MYK_ROOT, "python", "python.exe")) ||
    fs.existsSync(path.join(MYK_ROOT, "python", "Scripts", "python.exe"))
  );
}

function wikiDataRoot() {
  const fromEnv = (process.env.WIKI_ROOT || process.env.MYKKNOWLEDGE_ROOT || "").trim();
  if (fromEnv) return path.resolve(fromEnv);
  if (isBundledLayout()) {
    const local = process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local");
    return path.join(local, "Yizhi");
  }
  return MYK_ROOT;
}

/** 渠道码：data/channel.json 优先；否则从安装目录 channel.dat 补写一次 */
function resolveChannelCode(dataRoot) {
  const CODE_RE = /^P_[A-Z0-9_]{2,32}$/;
  const dataDir = path.join(dataRoot, "data");
  const jsonPath = path.join(dataDir, "channel.json");
  try {
    if (fs.existsSync(jsonPath)) {
      const j = JSON.parse(fs.readFileSync(jsonPath, "utf8"));
      const code = String(j.code || "")
        .trim()
        .toUpperCase();
      if (CODE_RE.test(code)) return code;
    }
  } catch {
    /* ignore */
  }
  const appChannel = path.join(MYK_ROOT, "channel.dat");
  try {
    if (!fs.existsSync(appChannel)) return "";
    const code = fs.readFileSync(appChannel, "utf8").trim().toUpperCase();
    if (!CODE_RE.test(code)) return "";
    try {
      fs.mkdirSync(dataDir, { recursive: true });
    } catch {
      /* ignore */
    }
    if (!fs.existsSync(jsonPath)) {
      fs.writeFileSync(
        jsonPath,
        JSON.stringify({ code, product: "yizhi", locked: true }, null, 2),
        "utf8"
      );
    }
    return code;
  } catch {
    return "";
  }
}

function loadAppIcon() {
  const dir = path.join(__dirname, "assets");
  const candidates =
    process.platform === "win32"
      ? ["icon-256.png", "icon.png", "icon.ico"]
      : ["icon.png", "icon-256.png", "icon.ico"];
  for (const name of candidates) {
    const p = path.join(dir, name);
    if (!fs.existsSync(p)) continue;
    const img = nativeImage.createFromPath(p);
    if (img && !img.isEmpty()) return img;
  }
  return null;
}

const APP_ICON = loadAppIcon();

if (process.platform === "win32") {
  app.commandLine.appendSwitch("high-dpi-support", "1");
  app.commandLine.appendSwitch("force-color-profile", "srgb");
  // 部分 Windows 环境会偶发 Network service crashed；改为进程内网络栈更稳。
  app.commandLine.appendSwitch("enable-features", "NetworkServiceInProcess");
}
// UI is loadFile (file://) while API is http://127.0.0.1 — Chromium Private Network
// Access otherwise blocks POSTs as TypeError: Failed to fetch.
app.commandLine.appendSwitch(
  "disable-features",
  "BlockInsecurePrivateNetworkRequests,PrivateNetworkAccessSendPreflights,PrivateNetworkAccessRespectPreflightResults"
);

let backendProc = null;
let backendOwned = false;
let mainWindow = null;

const FILE_VIEWER_MARKER = path.join(
  __dirname,
  "renderer",
  "vendor",
  "file-viewer",
  "flyfish-file-viewer-web-full.iife.js"
);

function npmCmd() {
  return process.platform === "win32" ? "npm.cmd" : "npm";
}

function fileViewerReady() {
  return fs.existsSync(FILE_VIEWER_MARKER);
}

function syncFileViewerAssets() {
  if (fileViewerReady()) return { ok: true, synced: false };
  const fvPkg = path.join(__dirname, "node_modules", "@file-viewer", "web-full");
  if (!fs.existsSync(fvPkg)) {
    execSync(`${npmCmd()} install`, { cwd: __dirname, stdio: "inherit" });
  }
  execSync(`${npmCmd()} run sync-file-viewer`, { cwd: __dirname, stdio: "inherit" });
  const ok = fileViewerReady();
  if (!ok) throw new Error("File-Viewer 同步后仍未就绪");
  return { ok: true, synced: true };
}

function openViewerFromUrl(url) {
  try {
    const u = new URL(url);
    if (u.pathname !== "/viewer") return false;
    const relPath = u.searchParams.get("path") || "";
    const filename = u.searchParams.get("name") || "";
    const page = parseInt(u.searchParams.get("page") || "0", 10) || 0;
    if (!relPath) return false;
    openViewerWindow(relPath, filename, page);
    return true;
  } catch {
    return false;
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const DOCUBROWSER_PORT = process.env.MYKKNOWLEDGE_DOCUBROWSER_PORT || "18766";
const QUIET_LAUNCH = isBundledLayout() && process.env.YIZHI_DEV !== "1";
/** Install/portable: hide console spam. Source-tree / YIZHI_DEV=1: show backend logs. */
const HIDE_BACKEND_LOGS = QUIET_LAUNCH || process.env.YIZHI_PORTABLE === "1";
let splashWindow = null;

function bundledPython() {
  const candidates =
    process.platform === "win32"
      ? [
          path.join(MYK_ROOT, "python", "python.exe"),
          path.join(MYK_ROOT, "python", "Scripts", "python.exe"),
        ]
      : [
          path.join(MYK_ROOT, "python", "bin", "python3"),
          path.join(MYK_ROOT, "python", "bin", "python"),
        ];
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  return process.platform === "win32" ? "python" : "python3";
}

/**
 * venv 留下的 pyvenv.cfg 会把 sys.prefix 指回开发机/父目录，
 * 导致找不到 python\Lib\site-packages（表现为 backend exited with code 1）。
 * 安装包构建时应删除；此处再清一次以兼容已发出的坏包。
 */
function sanitizeBundledPython() {
  const cfg = path.join(MYK_ROOT, "python", "pyvenv.cfg");
  if (!fs.existsSync(cfg)) return;
  try {
    fs.unlinkSync(cfg);
    bootLog("sanitizeBundledPython: removed pyvenv.cfg");
  } catch (e) {
    bootLog(`sanitizeBundledPython: cannot remove pyvenv.cfg: ${e.message || e}`);
  }
}

function pythonCmd() {
  return bundledPython();
}

/** @returns {{ cmd: string, args: string[] }} */
function backendLaunchSpec() {
  const frozen = bundledBackendExe();
  if (frozen) {
    return { cmd: frozen, args: [] };
  }
  // A1/A6: 安装版禁止静默回退到系统 python
  if (isInstalledLayout()) {
    const logHint = path.join(wikiDataRoot(), "backend.log");
    const frozenHint = path.join(wikiDataRoot(), "frozen-boot.log");
    throw new Error(
      "未找到后端引擎 runtime\\yizhi-backend.exe。\n" +
        "请重新安装易知完整安装包。\n\n" +
        `日志: ${logHint}\n` +
        `引擎日志: ${frozenHint}`
    );
  }
  return { cmd: pythonCmd(), args: ["-m", "backend"] };
}

function backendLogPath() {
  const dir =
    process.env.LOCALAPPDATA
      ? path.join(process.env.LOCALAPPDATA, "Yizhi")
      : path.join(os.homedir(), "AppData", "Local", "Yizhi");
  return path.join(dir, "backend.log");
}

function appendBackendLog(chunk) {
  try {
    const p = backendLogPath();
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.appendFileSync(p, chunk, "utf8");
  } catch {
    /* ignore */
  }
}

function readBackendLogTail(maxChars = 1200) {
  try {
    const p = backendLogPath();
    if (!fs.existsSync(p)) return "";
    const text = fs.readFileSync(p, "utf8");
    return text.length <= maxChars ? text : text.slice(-maxChars);
  } catch {
    return "";
  }
}

function readFrozenBootLogTail(maxChars = 800) {
  try {
    const p = path.join(wikiDataRoot(), "frozen-boot.log");
    if (!fs.existsSync(p)) return "";
    const text = fs.readFileSync(p, "utf8");
    return text.length <= maxChars ? text : text.slice(-maxChars);
  } catch {
    return "";
  }
}

function formatStartupFailureDetail(err) {
  const msg = String((err && err.message) || err || "未知错误");
  const parts = [msg];
  const be = readBackendLogTail(600).trim();
  const fr = readFrozenBootLogTail(400).trim();
  if (be) parts.push(`\n—— backend.log ——\n${be}`);
  if (fr) parts.push(`\n—— frozen-boot.log ——\n${fr}`);
  if (!msg.includes("日志:")) {
    parts.push(`\n日志目录: ${wikiDataRoot()}`);
  }
  return parts.join("\n");
}

function updateSplashStatus(message) {
  if (!splashWindow || splashWindow.isDestroyed()) return;
  const js = `window.setSplashStatus && window.setSplashStatus(${JSON.stringify(message)});`;
  splashWindow.webContents.executeJavaScript(js).catch(() => {});
}

function createSplashWindow() {
  const opts = {
    width: 480,
    height: 360,
    frame: false,
    // 透明窗在部分客户机永不触发 ready-to-show → 表现为控制台光标闪、无界面
    transparent: false,
    alwaysOnTop: true,
    center: true,
    resizable: false,
    skipTaskbar: false,
    show: true,
    backgroundColor: "#0f1419",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  };
  if (APP_ICON) opts.icon = APP_ICON;
  splashWindow = new BrowserWindow(opts);
  splashWindow.loadFile(path.join(__dirname, "splash.html"));
  splashWindow.once("ready-to-show", () => {
    if (splashWindow && !splashWindow.isDestroyed()) splashWindow.show();
  });
}

function closeSplashWindow() {
  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.close();
  }
  splashWindow = null;
}

function readTextFile(filePath) {
  if (!fs.existsSync(filePath)) return "";
  return fs.readFileSync(filePath, "utf8");
}

function upsertEnvLine(text, key, value) {
  const line = `${key}=${value}`;
  const re = new RegExp(`^${key}=.*$`, "m");
  if (re.test(text)) return text.replace(re, line);
  const sep = text && !text.endsWith("\n") ? "\n" : "";
  return `${text}${sep}${line}\n`;
}

function sanitizeUpdateUrl(raw) {
  const val = String(raw || "").trim();
  if (!val || /TrimEnd/i.test(val)) {
    return "https://www.yzwhysxx.cn/yizhi/latest.json";
  }
  return val;
}

function repairUserEnv(envDst) {
  let text = readTextFile(envDst);
  if (!text) return;

  let changed = false;
  const updateMatch = text.match(/^MYKNOWLEDGE_UPDATE_URL=(.*)$/m);
  if (updateMatch) {
    const fixed = sanitizeUpdateUrl(updateMatch[1]);
    if (fixed !== updateMatch[1].trim()) {
      text = upsertEnvLine(text, "MYKNOWLEDGE_UPDATE_URL", fixed);
      changed = true;
    }
  }

  const envUserPath = path.join(MYK_ROOT, ".env.user");
  if (fs.existsSync(envUserPath)) {
    const userText = readTextFile(envUserPath);
    for (const key of [
      "MYKNOWLEDGE_UPDATE_URL",
      "MYKNOWLEDGE_LICENSE_REQUIRED",
      "MYKNOWLEDGE_LICENSE_SERVER",
      "MYKNOWLEDGE_LICENSE_JWT_SECRET",
    ]) {
      const srcMatch = userText.match(new RegExp(`^${key}=(.*)$`, "m"));
      if (!srcMatch) continue;
      let srcVal = srcMatch[1].trim();
      if (key === "MYKNOWLEDGE_UPDATE_URL") srcVal = sanitizeUpdateUrl(srcVal);
      const dstMatch = text.match(new RegExp(`^${key}=(.*)$`, "m"));
      const dstVal = dstMatch ? dstMatch[1].trim() : "";
      const broken = key === "MYKNOWLEDGE_UPDATE_URL" && /TrimEnd/i.test(dstVal);
      if (!dstVal || broken) {
        text = upsertEnvLine(text, key, srcVal);
        changed = true;
      }
    }
  }

  if (changed) {
    fs.writeFileSync(envDst, text, "utf8");
  }
}

function ensureUserEnv() {
  const dataRoot = wikiDataRoot();
  fs.mkdirSync(dataRoot, { recursive: true });
  const envDst = path.join(dataRoot, ".env");
  if (!fs.existsSync(envDst)) {
    for (const src of [path.join(MYK_ROOT, ".env.user"), path.join(MYK_ROOT, ".env.example")]) {
      if (fs.existsSync(src)) {
        fs.copyFileSync(src, envDst);
        break;
      }
    }
  }
  repairUserEnv(envDst);
}

function parseDotEnv(text) {
  const out = {};
  for (const line of String(text || "").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq < 1) continue;
    const key = trimmed.slice(0, eq).trim();
    let val = trimmed.slice(eq + 1).trim();
    if (
      (val.startsWith('"') && val.endsWith('"')) ||
      (val.startsWith("'") && val.endsWith("'"))
    ) {
      val = val.slice(1, -1);
    }
    if (key) out[key] = val;
  }
  return out;
}

function loadUserEnvMap(dataRoot) {
  const envDst = path.join(dataRoot, ".env");
  repairUserEnv(envDst);
  if (!fs.existsSync(envDst)) return {};
  const parsed = parseDotEnv(readTextFile(envDst));
  const updateKey = "MYKNOWLEDGE_UPDATE_URL";
  if (parsed[updateKey]) {
    parsed[updateKey] = sanitizeUpdateUrl(parsed[updateKey]);
  }
  return parsed;
}

function buildBackendEnv(extra = {}) {
  const dataRoot = wikiDataRoot();
  const userEnv = loadUserEnvMap(dataRoot);
  return {
    ...process.env,
    ...userEnv,
    MYK_ROOT,
    YIZHI_APP_ROOT: MYK_ROOT,
    WIKI_ROOT: dataRoot,
    MYKNOWLEDGE_ROOT: dataRoot,
    PYTHONIOENCODING: "utf-8",
    ...extra,
  };
}

function wikiHasInbox() {
  const root = wikiDataRoot();
  return (
    fs.existsSync(path.join(root, "inbox")) ||
    fs.existsSync(path.join(root, "purpose.md")) ||
    fs.existsSync(path.join(root, "notes"))
  );
}

function runPython(args, cwd = MYK_ROOT) {
  return new Promise((resolve, reject) => {
    const env = buildBackendEnv();
    const proc = spawn(pythonCmd(), args, {
      cwd,
      env,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
    let stderr = "";
    let stdout = "";
    proc.stderr?.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    proc.stdout?.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    proc.on("error", reject);
    proc.on("exit", (code) => {
      if (code === 0) {
        resolve();
        return;
      }
      const detail = (stderr || stdout).trim().split(/\r?\n/).filter(Boolean).slice(-6).join(" | ");
      reject(
        new Error(
          detail
            ? `python exited with code ${code}: ${detail}`
            : `python exited with code ${code}`
        )
      );
    });
  });
}

async function runBootstrap() {
  bootLog("bootstrap: start");
  if (!fileViewerReady()) {
    throw new Error("文件预览组件未就绪，请重新安装易知");
  }

  updateSplashStatus("正在释放端口…");
  bootLog("bootstrap: killPort");
  killPort(PORT);
  killPort(DOCUBROWSER_PORT);
  await sleep(400);

  updateSplashStatus("正在准备用户数据…");
  bootLog("bootstrap: ensureUserEnv");
  sanitizeBundledPython();
  ensureUserEnv();

  const hasPy = hasBundledPythonExe();
  if (hasPy && fs.existsSync(path.join(MYK_ROOT, "scripts", "setup_docubrowser.py"))) {
    updateSplashStatus("正在检查 DocuBrowser…");
    bootLog("bootstrap: setup_docubrowser");
    try {
      await runPython([path.join("scripts", "setup_docubrowser.py")]);
    } catch {
      /* 非致命，后端仍可启动 */
    }
  } else if (!hasPy) {
    bootLog("bootstrap: skip setup_docubrowser (no bundled python; A1 frozen-only)");
  }

  if (!wikiHasInbox()) {
    if (hasPy) {
      updateSplashStatus("正在初始化知识库…");
      bootLog("bootstrap: wiki init");
      try {
        await runPython(["-m", "lib.cli", "init"]);
      } catch (e) {
        throw new Error(`知识库初始化失败: ${e.message || e}`);
      }
    } else {
      // A1：无 python\ 时由 FastAPI startup 建 inbox/assets
      bootLog("bootstrap: skip wiki cli init (backend will scaffold inbox)");
      try {
        fs.mkdirSync(path.join(wikiDataRoot(), "inbox"), { recursive: true });
        fs.mkdirSync(path.join(wikiDataRoot(), "assets"), { recursive: true });
      } catch {
        /* ignore */
      }
    }
  }

  updateSplashStatus("正在启动引擎…");
  bootLog("bootstrap: startBackend");
  await startBackend();
  bootLog("bootstrap: done");
}

function fetchJson(urlPath, timeoutMs = 8000) {
  return new Promise((resolve) => {
    const req = http.get(`${API}${urlPath}`, (res) => {
      let body = "";
      res.on("data", (chunk) => {
        body += chunk;
      });
      res.on("end", () => {
        if (res.statusCode !== 200) {
          resolve(null);
          return;
        }
        try {
          resolve(JSON.parse(body));
        } catch {
          resolve(null);
        }
      });
    });
    req.on("error", () => resolve(null));
    req.setTimeout(timeoutMs, () => {
      try {
        req.destroy();
      } catch {
        /* ignore */
      }
      resolve(null);
    });
  });
}

let backendProbeInFlight = null;

async function backendIsCurrent() {
  if (backendProbeInFlight) return backendProbeInFlight;
  backendProbeInFlight = (async () => {
    const health = await fetchJson("/api/health", 3000);
    if (!health?.ok) return false;
    const caps = health.capabilities || [];
    return caps.includes("ask_stream");
  })();
  try {
    return await backendProbeInFlight;
  } finally {
    backendProbeInFlight = null;
  }
}

function killPort(port) {
  const p = String(port);
  try {
    if (process.platform === "win32") {
      // 禁止 Get-NetTCPConnection：部分客户机上会永久挂起（表现为 cmd 光标闪、无窗口）
      let out = "";
      try {
        out = execSync(`netstat -ano -p tcp`, {
          encoding: "utf8",
          windowsHide: true,
          timeout: 5000,
        });
      } catch {
        return;
      }
      const pids = new Set();
      const needle = `:${p}`;
      for (const line of out.split(/\r?\n/)) {
        if (!/LISTENING/i.test(line)) continue;
        if (!line.includes(needle)) continue;
        // 避免把 :187650 之类误杀：要求端口后接空白
        if (!new RegExp(`:${p}\\s`).test(line) && !new RegExp(`\\]:${p}\\s`).test(line)) {
          continue;
        }
        const parts = line.trim().split(/\s+/);
        const pid = parts[parts.length - 1];
        if (pid && /^\d+$/.test(pid) && pid !== "0") pids.add(pid);
      }
      for (const pid of pids) {
        try {
          execSync(`taskkill /PID ${pid} /F`, {
            stdio: "ignore",
            windowsHide: true,
            timeout: 3000,
          });
        } catch {
          /* ignore */
        }
      }
    } else {
      execSync(`lsof -ti :${p} | xargs kill -9 2>/dev/null || true`, {
        stdio: "ignore",
        timeout: 5000,
      });
    }
  } catch {
    /* port may already be free */
  }
}

function spawnBackendOnce() {
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (err) => {
      if (settled) return;
      settled = true;
      if (err) reject(err);
      else resolve();
    };

    const dataRoot = wikiDataRoot();
    const channelCode = resolveChannelCode(dataRoot);
    if (channelCode) bootLog(`channel=${channelCode}`);
    const env = buildBackendEnv({
      MYKNOWLEDGE_PORT: PORT,
      MYKNOWLEDGE_DEVICE_ID: computeDeviceId(),
      ...(channelCode ? { YIZHI_CHANNEL: channelCode, ZHOUYI_CHANNEL: channelCode } : {}),
    });
    const { cmd, args } = backendLaunchSpec();
    try {
      fs.writeFileSync(
        backendLogPath(),
        `${new Date().toISOString()} spawn ${cmd} ${args.join(" ")}\n`,
        "utf8"
      );
    } catch {
      /* ignore */
    }
    bootLog(`spawnBackend: ${cmd} ${args.join(" ")}`);
    // PyInstaller onedir：工作目录必须是 exe 所在目录，否则偶发 LoadLibrary python3xx.dll 失败
    const spawnCwd = bundledBackendExe() ? path.dirname(cmd) : MYK_ROOT;
    backendProc = spawn(cmd, args, {
      cwd: spawnCwd,
      env,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
    backendOwned = true;
    backendProc.stdout.on("data", (d) => {
      const s = d.toString();
      appendBackendLog(s);
      if (!HIDE_BACKEND_LOGS) process.stdout.write(s);
    });
    backendProc.stderr.on("data", (d) => {
      const s = d.toString();
      appendBackendLog(s);
      if (!HIDE_BACKEND_LOGS) process.stdout.write(s);
    });
    backendProc.on("error", (err) => finish(err));
    backendProc.on("exit", (code) => {
      if (!settled && code !== 0) {
        finish(
          new Error(
            formatStartupFailureDetail(new Error(`后端进程异常退出（代码 ${code}）`))
          )
        );
      }
    });

    let tries = 0;
    updateSplashStatus("正在启动引擎…");
    const tick = async () => {
      if (settled) return;
      if (await backendIsCurrent()) {
        updateSplashStatus("服务已就绪…");
        finish();
        return;
      }
      // Bundled first launch can spend 30–60s in FastAPI startup (license/scaffold).
      if (tries === 2) updateSplashStatus("正在检查服务…");
      if (tries === 40) updateSplashStatus("首次启动可能需要约一分钟…");
      if (tries === 120) updateSplashStatus("仍在等待引擎，请稍候…");
      if (++tries < 200) setTimeout(tick, 250);
      else {
        const detail = formatStartupFailureDetail(
          new Error("后端未在时限内就绪（端口 18765 可能被占用或引擎启动失败）")
        );
        finish(new Error(detail));
      }
    };
    setTimeout(tick, 500);
  });
}

function killFrozenBackendProcesses() {
  if (process.platform !== "win32") return;
  try {
    execSync('taskkill /F /IM yizhi-backend.exe /T', {
      stdio: "ignore",
      windowsHide: true,
      timeout: 8000,
    });
  } catch {
    /* none running */
  }
}

async function startBackend() {
  if (await backendIsCurrent()) return;

  let lastError = null;
  for (let attempt = 0; attempt < 3; attempt++) {
    killPort(PORT);
    // 避免叠开多个 onedir 进程抢加载 python313.dll（会报「内存资源不足」）
    killFrozenBackendProcesses();
    await sleep(800 + attempt * 500);
    try {
      await spawnBackendOnce();
      if (await backendIsCurrent()) return;
    } catch (err) {
      lastError = err;
      if (backendProc) {
        try {
          backendProc.kill();
        } catch {
          /* ignore */
        }
        backendProc = null;
        backendOwned = false;
      }
      killFrozenBackendProcesses();
    }
  }
  throw lastError || new Error("backend failed to start on port 18765");
}

function createWindow() {
  const winOpts = {
    width: 1100,
    height: 760,
    minWidth: 900,
    minHeight: 560,
    title: "易知",
    backgroundColor: "#e8ecf2",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  };
  if (APP_ICON) winOpts.icon = APP_ICON;
  mainWindow = new BrowserWindow(winOpts);
  mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));
  mainWindow.setMenuBarVisibility(false);
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith(API) && openViewerFromUrl(url)) {
      return { action: "deny" };
    }
    shell.openExternal(url);
    return { action: "deny" };
  });
}

function openViewerWindow(relPath, filename, page = 0) {
  const winOpts = {
    width: 1080,
    height: 820,
    minWidth: 720,
    minHeight: 480,
    title: filename ? `${filename} · 预览` : "文件预览 · 易知",
    backgroundColor: "#f3f6fa",
    webPreferences: {
      preload: path.join(__dirname, "viewer-preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  };
  if (APP_ICON) winOpts.icon = APP_ICON;
  const win = new BrowserWindow(winOpts);
  const q = new URLSearchParams({
    path: relPath,
    name: filename || "",
  });
  if (page && Number(page) > 0) q.set("page", String(Number(page)));
  win.loadURL(`${API}/viewer?${q.toString()}`);
  win.setMenuBarVisibility(false);
  win.webContents.setWindowOpenHandler(({ url }) => {
    // 预览窗内禁止把本地文件 API 交给外部浏览器（否则会直接下载）
    if (url.startsWith(API)) return { action: "deny" };
    shell.openExternal(url);
    return { action: "deny" };
  });
}

ipcMain.handle("pick-directory", async () => {
  const r = await dialog.showOpenDialog({
    properties: ["openDirectory", "dontAddToRecent"],
    title: "选择外联文档目录",
    buttonLabel: "选择此文件夹",
  });
  if (r.canceled || !r.filePaths?.length) return null;
  return r.filePaths[0];
});

app.whenReady().then(async () => {
  ipcMain.handle("ensure-file-viewer", () => {
    try {
      return syncFileViewerAssets();
    } catch (e) {
      return { ok: false, error: String(e.message || e) };
    }
  });
  ipcMain.handle("open-asset-viewer", (_event, payload) => {
    const relPath = payload?.path || "";
    const filename = payload?.filename || "";
    const page = payload?.page || 0;
    if (relPath) openViewerWindow(relPath, filename, page);
  });
  ipcMain.handle("get-app-info", () => ({
    version: pkg.version || "0.0.0",
    name: pkg.description || "易知",
  }));
  ipcMain.handle("open-external", (_event, url) => {
    if (typeof url !== "string" || !/^https?:\/\//i.test(url.trim())) {
      return { ok: false, error: "invalid url" };
    }
    shell.openExternal(url.trim());
    return { ok: true };
  });
  ipcMain.handle("open-asset-system", async (_event, payload) => {
    const relPath = payload?.path || "";
    const filename = payload?.filename || path.basename(relPath) || "file";
    if (!relPath) return { ok: false, error: "missing path" };
    try {
      const res = await fetch(
        `${API}/api/assets/file?path=${encodeURIComponent(relPath)}&inline=1`
      );
      if (!res.ok) {
        return { ok: false, error: `HTTP ${res.status}` };
      }
      const buf = Buffer.from(await res.arrayBuffer());
      const safeName = filename.replace(/[<>:"/\\|?*]/g, "_");
      const tmp = path.join(os.tmpdir(), `yizhi-${Date.now()}-${safeName}`);
      fs.writeFileSync(tmp, buf);
      const err = await shell.openPath(tmp);
      return err ? { ok: false, error: err } : { ok: true, path: tmp };
    } catch (e) {
      return { ok: false, error: String(e.message || e) };
    }
  });
  if (process.platform === "win32") {
    app.setAppUserModelId("com.yiwensheng.yizhi");
  }
  Menu.setApplicationMenu(null);
  try {
    bootLog("whenReady: createSplash");
    // 尽早出启动画面，避免 killPort/backend 阶段长时间无窗口
    createSplashWindow();
    updateSplashStatus("正在启动…");
    bootLog(`whenReady: QUIET_LAUNCH=${QUIET_LAUNCH} backend=${backendLaunchSpec().cmd}`);
    if (QUIET_LAUNCH) {
      await runBootstrap();
    } else {
      if (!fileViewerReady()) {
        updateSplashStatus("正在准备文件预览组件…");
        bootLog("whenReady: syncFileViewerAssets");
        console.log("[易知] 首次使用，正在安装文件预览组件…");
        syncFileViewerAssets();
      }
      updateSplashStatus("正在启动 AI 服务…");
      bootLog("whenReady: startBackend");
      console.log("[易知] 正在启动 AI 服务（backend）…");
      await startBackend();
      bootLog("whenReady: backend ready");
      console.log("[易知] AI 服务已就绪");
    }
    bootLog("whenReady: createWindow");
    closeSplashWindow();
    createWindow();
    bootLog("whenReady: main window created");
  } catch (e) {
    bootLog(`whenReady FAIL: ${e && e.message ? e.message : e}`);
    closeSplashWindow();
    const withLog = formatStartupFailureDetail(e);
    dialog.showErrorBox(
      "易知启动失败",
      withLog.length > 1800 ? withLog.slice(0, 1800) + "…" : withLog
    );
    console.error(e);
    app.quit();
  }
});

app.on("window-all-closed", () => {
  if (backendOwned && backendProc) backendProc.kill();
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
