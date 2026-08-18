# 易知后端二进制化（PyInstaller 为主 · Nuitka 备选）与 YizhiStart.vbs 对接 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将安装包内可见的 Python 解释器 + 大量 `.py` 源码，收敛为可静默启动的 `yizhi-backend.exe`（及必要依赖目录），并与现有 `YizhiStart.vbs` / `electron/main.js` 启动链无缝对接；开发树启动方式保持不变。

**Architecture:** Electron 仍负责 UI 与 bootstrap；后端入口从 `python\python.exe -m backend` 改为优先 `runtime\yizhi-backend.exe`（PyInstaller **onedir**）。VBS 仅负责探测运行时存在性并静默拉起 Electron（不直接 spawn 后端）。`main.js` 统一解析「后端可执行文件」；缺二进制时回退到内置 `python\python.exe`，保证过渡期与开发机兼容。Nuitka 作为 Phase B 对照实验，产出同一可执行文件名与同一目录契约，避免分叉两套启动逻辑。

**Tech Stack:** Python 3.10–3.13、PyInstaller 6.x、（可选）Nuitka、FastAPI/Uvicorn、`requirements-runtime.txt`、PowerShell 构建脚本、Inno Setup、现有 `YizhiStart.vbs` + `electron/main.js`。

---

## 0. 决策写死（本计划权威结论）

### 0.1 默认采用：**PyInstaller onedir**

| 维度 | PyInstaller | Nuitka |
|------|-------------|--------|
| 构建速度 | 快（分钟级） | 慢（可达十余分钟～数十分钟） |
| FastAPI / uvicorn / 动态 import | 成熟；`hiddenimports` 有社区经验 | 需额外 `plugin` / 强制包含模块，踩坑成本高 |
| 体积 | onedir 偏大但可接受 | 有时更小，但首次编译 + MSVC 依赖重 |
| 杀软误报 | onefile 更严重；**onedir 明显更稳** | 略好但非银弹 |
| 与现有「拷整份 Python」迁移 | 文档已预留 pyinstaller 路径 | 方案文档未预留 |
| 排障 | 仍可用 `--debug` / 控制台版对比 | 晦涩 |

**结论：**

1. **正式发版路径：PyInstaller `onedir`，控制台子系统关闭（`console=False`），入口名固定 `yizhi-backend.exe`。**
2. **目录契约（安装根相对）：**

```text
{app}/
  runtime/
    yizhi-backend.exe          # 主入口
    _internal/                 # PyInstaller 依赖（勿手改）
  electron/                    # 不变
  YizhiStart.vbs               # 探测 runtime\yizhi-backend.exe 或 fallback python\
  prompts/ / skills/ / …        # 仍可由后端按 MYK_ROOT 读（非 Python site-packages）
```

3. **Nuitka：** 仅 Phase B 在 CI/开发机构建同一路径 `runtime\yizhi-backend.exe` 做 A/B；**启动脚本与 VBS 不区分编译器**，只认文件是否存在与 `--health`/`/api/health` 是否通。
4. **不采用 onefile**：启动慢、易被杀软隔离、难热修 `_internal`。
5. **安装包过渡：** `build-portable.ps1 -ForInstaller` 增加开关 `-BackendBinary`（默认 **开**）。失败时构建脚本可 `-SkipBackendBinary` 回退旧「整份 python\」策略，避免堵发版。

### 0.2 与 `YizhiStart.vbs` 的职责边界（写死）

| 组件 | 负责 | 不负责 |
|------|------|--------|
| `YizhiStart.vbs` | 校验「后端运行时」存在；设 `MYK_ROOT` / `WIKI_ROOT` / `ELECTRON_NO_ATTACH_CONSOLE`；静默 `electron.exe .` | **不**直接启动 backend；不解析 `-m backend` |
| `electron/main.js` | 选 `backendExecutable()`；`spawn(exe, args)`；写 `backend.log`；splash | 不负责打包 |
| `build-backend-exe.ps1` | 产出 `runtime\` | 不改 Inno Icons |

VBS 今日用 `ResolvePythonExe` **仅为证明内置解释器完整**；二进制化后改为 `ResolveBackendRuntime`：优先 `runtime\yizhi-backend.exe`，否则回退 `python\python.exe`。电子进程仍按现路径启动。

### 0.3 后端进程启动契约（写死）

`main.js` 今天：

```js
spawn(pythonCmd(), ["-m", "backend"], { cwd: MYK_ROOT, env, ... })
```

二进制化后：

```js
const { cmd, args } = backendLaunchSpec();
// Frozen: cmd = .../runtime/yizhi-backend.exe , args = []
// Dev / fallback: cmd = python.exe , args = ["-m", "backend"]
spawn(cmd, args, { cwd: MYK_ROOT, env, windowsHide: true, ... })
```

入口模块（新建）在 frozen 模式下直接调用与 `python -m backend` 相同的 `uvicorn` 启动路径。

### 0.4 明确不做（YAGNI）

- 不把 Electron / renderer 打进同一 exe。
- 不删除开发树对系统 Python 的依赖。
- 不把 DocuBrowser 整树静态链进 backend exe；保持现有 `third_party` 旁路（GPL 说明仍适用）。
- 不在本计划内上 electron-builder（另案）。

---

## 1. 文件地图（将创建 / 修改）

| 路径 | 职责 |
|------|------|
| **Create** `backend/__frozen_main__.py` | PyInstaller/Nuitka 共用入口：启动 uvicorn / `backend.server:app` |
| **Create** `scripts/packaging/yizhi-backend.spec` | PyInstaller spec（onedir、console=False、hiddenimports） |
| **Create** `scripts/build-backend-exe.ps1` | 调用 PyInstaller，拷贝到 staging/`runtime` |
| **Create** `scripts/packaging/nuitka-backend.ps1` | Phase B：Nuitka 构建，产出覆盖同路径 |
| **Create** `tests/test_backend_frozen_entry.py` | 入口可导入、健康路径常量 |
| **Create** `docs/commercial/后端二进制化.md` | 运维向说明（可与本计划交叉链接） |
| **Modify** `electron/main.js` | `isBundledLayout` / `backendLaunchSpec` / spawn |
| **Modify** `scripts/installer/YizhiStart.vbs` | `ResolveBackendRuntime` |
| **Modify** `scripts/build-portable.ps1` | 调用 build-backend-exe；可选不拷整份 Python |
| **Modify** `scripts/build-installer.ps1` | staging 自检：`runtime\yizhi-backend.exe` |
| **Modify** `scripts/installer/YizhiSetup.iss` | 如需声明新目录（通常 recursesubdirs 已够） |
| **Modify** `docs/commercial/构建安装包.md` | 发版步骤增加二进制产物检查 |
| **Modify** `scripts/installer/patch-installed.ps1` | 可同步新 VBS |

---

## 2. 目标安装目录（二进制模式）

```text
C:\Program Files\Yizhi\
  runtime\
    yizhi-backend.exe
    _internal\...
  electron\...
  prompts\
  skills\
  product\
  third_party\...          # ffmpeg / bun / DocuBrowser（保持旁路）
  YizhiStart.vbs
  YizhiStart.bat
  .env.user                 # 或安装后复制到 %LOCALAPPDATA%\Yizhi
```

用户数据仍在 `%LOCALAPPDATA%\Yizhi`（`WIKI_ROOT`），与今日一致。

**可选瘦身：** 正式包不再捆绑完整 `python\`（仅保留 `runtime\`）。过渡期可双轨：两者皆有时 **优先 runtime**。

---

## Task 1: Frozen 入口与单元测试（TDD）

**Files:**
- Create: `backend/__frozen_main__.py`
- Create: `tests/test_backend_frozen_entry.py`
- Read: `backend/__main__.py`（对齐现有启动）

- [ ] **Step 1: 读现有入口**

打开 `e:\app\Myknowledge\backend\__main__.py`，确认当前如何启动 uvicorn（host/port/app 路径）。记录端口默认 `18765` 与环境变量名。

- [ ] **Step 2: 写失败测试**

```python
# tests/test_backend_frozen_entry.py
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_frozen_main_exports_run():
    from backend.__frozen_main__ import run_backend

    assert callable(run_backend)


def test_frozen_main_resolves_app_import():
    from backend.__frozen_main__ import get_asgi_app

    app = get_asgi_app()
    assert app is not None
    assert hasattr(app, "router") or callable(app)
```

- [ ] **Step 3: 跑测试确认失败**

```powershell
cd E:\app\Myknowledge
python -m pytest tests/test_backend_frozen_entry.py -q --tb=line
```

Expected: `ModuleNotFoundError` 或 `ImportError` for `backend.__frozen_main__`.

- [ ] **Step 4: 实现最小入口**

```python
# backend/__frozen_main__.py
"""Entry for PyInstaller / Nuitka frozen backend (same behavior as `python -m backend`)."""

from __future__ import annotations

import os
import sys


def get_asgi_app():
    from backend.server import app

    return app


def run_backend() -> None:
    import uvicorn

    host = os.environ.get("MYKNOWLEDGE_HOST", "127.0.0.1")
    port = int(os.environ.get("MYKNOWLEDGE_PORT", "18765"))
    # mirror __main__.py flags if any (reload=False for frozen)
    uvicorn.run(get_asgi_app(), host=host, port=port, log_level="info")


def main() -> None:
    run_backend()


if __name__ == "__main__":
    main()
```

若 `__main__.py` 有额外逻辑（信任路径、dotenv），**复制进** `run_backend()` 前，保持行为一致。

- [ ] **Step 5: 再跑测试**

```powershell
python -m pytest tests/test_backend_frozen_entry.py -q --tb=line
```

Expected: PASS.

- [ ] **Step 6: Commit（仅当用户要求提交时执行）**

```powershell
git add backend/__frozen_main__.py tests/test_backend_frozen_entry.py
git commit -m "feat(backend): add frozen entry for packaged yizhi-backend.exe"
```

---

## Task 2: PyInstaller spec + 构建脚本

**Files:**
- Create: `scripts/packaging/yizhi-backend.spec`
- Create: `scripts/build-backend-exe.ps1`
- Read: `requirements-runtime.txt`

- [ ] **Step 1: 安装构建依赖（开发机一次性）**

```powershell
cd E:\app\Myknowledge
python -m pip install "pyinstaller>=6.3" -r requirements-runtime.txt
```

- [ ] **Step 2: 写 spec（onedir、无控制台）**

```python
# scripts/packaging/yizhi-backend.spec
# -*- mode: python ; coding: utf-8 -*-
# Run from repo root: pyinstaller scripts/packaging/yizhi-backend.spec

block_cipher = None

hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "fastapi",
    "starlette",
    "anyio",
    "anyio._backends._asyncio",
    "pydantic",
    "yaml",
    "multipart",
    "backend",
    "backend.server",
    "lib",
]

a = Analysis(
    ["../../backend/__frozen_main__.py"],
    pathex=["../.."],
    binaries=[],
    datas=[],  # prompts/skills 不打进 exe，运行时读 MYK_ROOT
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="yizhi-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # 无黑窗；日志走 backend.log / uvicorn handlers
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="yizhi-backend",
)
```

注意：`Analysis` 里 `pathex` / 脚本路径以 **从仓库根执行 pyinstaller** 为准；若 relative 易碎，在 `build-backend-exe.ps1` 里 `Set-Location` 到仓库根并传绝对路径生成临时 spec。

- [ ] **Step 3: 写 `build-backend-exe.ps1`**

```powershell
#Requires -Version 5.1
param(
    [string]$OutDir = "",
    [switch]$Clean
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) { $OutDir = Join-Path $Root "dist\backend-runtime" }
$work = Join-Path $Root "dist\pyinstaller-work"
$spec = Join-Path $PSScriptRoot "packaging\yizhi-backend.spec"

if ($Clean) {
    Remove-Item $work, (Join-Path $Root "dist\yizhi-backend") -Recurse -Force -ErrorAction SilentlyContinue
}

New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
Push-Location $Root
try {
    python -m PyInstaller --noconfirm --distpath (Join-Path $Root "dist") --workpath $work $spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed: $LASTEXITCODE" }
} finally {
    Pop-Location
}

$built = Join-Path $Root "dist\yizhi-backend"
if (-not (Test-Path (Join-Path $built "yizhi-backend.exe"))) {
    throw "Missing dist\yizhi-backend\yizhi-backend.exe"
}

# Flatten into OutDir (= runtime/)
if (Test-Path $OutDir) { Remove-Item $OutDir -Recurse -Force }
Copy-Item $built $OutDir -Recurse
Write-Host "OK: $OutDir\yizhi-backend.exe"
```

- [ ] **Step 4: 本机构建并冒烟**

```powershell
cd E:\app\Myknowledge
.\scripts\build-backend-exe.ps1 -Clean
$env:MYK_ROOT = "E:\app\Myknowledge"
$env:WIKI_ROOT = "$env:TEMP\yizhi-bin-smoke"
New-Item $env:WIKI_ROOT -ItemType Directory -Force | Out-Null
# 短时启动
Start-Process -FilePath ".\dist\backend-runtime\yizhi-backend.exe" -WorkingDirectory $env:MYK_ROOT -PassThru | Out-Null
Start-Sleep -Seconds 4
Invoke-WebRequest "http://127.0.0.1:18765/api/health" -UseBasicParsing | Select-Object StatusCode
# 结束后手动 taskkill /IM yizhi-backend.exe /F
```

Expected: StatusCode `200`。若失败，查看 `%LOCALAPPDATA%\Yizhi\backend.log`（若入口尚未写日志，临时将 `console=True` 重建一次看 stderr）。

常见补救：向 `hiddenimports` 追加报错模块名（如 `email.mime`、`pydantic_core`），重建。

- [ ] **Step 5: Commit（用户要求时）**

```powershell
git add scripts/packaging/yizhi-backend.spec scripts/build-backend-exe.ps1
git commit -m "build: add PyInstaller onedir recipe for yizhi-backend"
```

---

## Task 3: `electron/main.js` 对接 `backendLaunchSpec`

**Files:**
- Modify: `electron/main.js`（`isBundledLayout`、`bundledPython`、`spawnBackendOnce` 一带）

- [ ] **Step 1: 扩展布局探测**

在 `isBundledLayout()` 旁增加：

```js
function bundledBackendExe() {
  const p = path.join(MYK_ROOT, "runtime", "yizhi-backend.exe");
  return fs.existsSync(p) ? p : "";
}

function isBundledLayout() {
  return (
    process.env.YIZHI_INSTALLED === "1" ||
    process.env.YIZHI_PORTABLE === "1" ||
    !!bundledBackendExe() ||
    fs.existsSync(path.join(MYK_ROOT, "python", "python.exe")) ||
    fs.existsSync(path.join(MYK_ROOT, "python", "Scripts", "python.exe"))
  );
}

/** @returns {{ cmd: string, args: string[] }} */
function backendLaunchSpec() {
  const frozen = bundledBackendExe();
  if (frozen) return { cmd: frozen, args: [] };
  return { cmd: pythonCmd(), args: ["-m", "backend"] };
}
```

- [ ] **Step 2: 改 `spawnBackendOnce`**

将：

```js
backendProc = spawn(pythonCmd(), ["-m", "backend"], { ... });
```

改为：

```js
const { cmd, args } = backendLaunchSpec();
bootLog(`spawnBackend: ${cmd} ${args.join(" ")}`);
backendProc = spawn(cmd, args, {
  cwd: MYK_ROOT,
  env: { ...process.env, MYK_ROOT, WIKI_ROOT: process.env.WIKI_ROOT || MYK_ROOT },
  windowsHide: true,
  stdio: ["ignore", "pipe", "pipe"],
});
```

保留现有 stdout/stderr → `backend.log`。

- [ ] **Step 3: 其它 `spawn(pythonCmd(), …)`**（init_wiki / setup_docubrowser）

凡安装版仍需跑短脚本处：

- 若存在 `runtime\yizhi-backend.exe`：**不要**假设 exe 能跑任意 `-c`；短脚本继续用 `python\python.exe` **或** 把逻辑迁入 backend HTTP API。
- **本阶段策略（写死）：** 二进制模式下 `build-portable` **仍可保留精简 `python\` 仅用于一次性 setup**；或缺 setup 时在 Electron bootstrap 改为纯 Node / 已内置进 first-run API。优先：**首次安装所需的 init 已在 staging 完成**，用户机尽量零 `python -m scripts…`。核对 `runBootstrap` / `setup_docubrowser`：若二进制包可跳过，则用 env `YIZHI_BACKEND_FROZEN=1` 跳过。

- [ ] **Step 4: 开发机验证**

无 `runtime\` 时行为与今天完全一致。手动放一份 `runtime\yizhi-backend.exe` 到开发树旁测启动。

---

## Task 4: `YizhiStart.vbs` 探测运行时

**Files:**
- Modify: `scripts/installer/YizhiStart.vbs`
- Modify: `scripts/build-portable.ps1`（拷贝 VBS；ASCII 校验不变）

- [ ] **Step 1: 替换 Resolve 函数**

```vb
Function ResolveBackendRuntime(installDir)
  Dim frozen, a, b
  frozen = installDir & "\runtime\yizhi-backend.exe"
  a = installDir & "\python\python.exe"
  b = installDir & "\python\Scripts\python.exe"
  If gFso.FileExists(frozen) Then
    ResolveBackendRuntime = frozen
  ElseIf gFso.FileExists(a) Then
    ResolveBackendRuntime = a
  ElseIf gFso.FileExists(b) Then
    ResolveBackendRuntime = b
  Else
    ResolveBackendRuntime = ""
  End If
End Function
```

- [ ] **Step 2: 启动前检查改用新函数**

将 `pythonExe = ResolvePythonExe(installDir)` 改为 `runtimeExe = ResolveBackendRuntime(installDir)`。缺失时 MsgBox 英文（保持 ASCII）：

```vb
"Yizhi backend runtime was not found." & vbCrLf & _
"Expected: " & installDir & "\runtime\yizhi-backend.exe" & vbCrLf & _
"or: " & installDir & "\python\python.exe"
```

VBS **仍只启动 Electron**；不传 runtime 路径给 Electron（Electron 自查 `MYK_ROOT\runtime`）。可选：`env("YIZHI_BACKEND_FROZEN") = "1"` 当 frozen 存在时。

- [ ] **Step 3: ASCII 校验**

```powershell
# build-portable 已有 CJK 检查；改完后必须再跑一次构建拷贝
```

---

## Task 5: 接入 `build-portable.ps1` / `build-installer.ps1`

**Files:**
- Modify: `scripts/build-portable.ps1`
- Modify: `scripts/build-installer.ps1`
- Modify: `docs/commercial/构建安装包.md`

- [ ] **Step 1: 参数**

```powershell
param(
    ...
    [switch]$SkipBackendBinary,  # 回退整份 python\
    [switch]$BackendBinary       # 默认：$ForInstaller 时视为 $true
)
```

逻辑：

```powershell
$useBinary = $ForInstaller -and -not $SkipBackendBinary
if ($BackendBinary) { $useBinary = $true }

if ($useBinary) {
    & (Join-Path $PSScriptRoot "build-backend-exe.ps1") -OutDir (Join-Path $OutputDir "runtime") -Clean
    if ($LASTEXITCODE -ne 0) { throw "backend binary build failed" }
    # 可选：不再 Copy-PythonTree；或保留精简 python 作 fallback
}
```

- [ ] **Step 2: staging 自检（installer）**

在 `build-installer.ps1` `$required` 列表增加：

```powershell
(Join-Path $StagingDir "runtime\yizhi-backend.exe")
```

若 `-SkipBackendBinary`，改回检查 `python\python.exe`。

- [ ] **Step 3: 文档**

在 `docs/commercial/构建安装包.md`「脚本会做什么」增加一条：

> 安装包默认构建 `runtime\yizhi-backend.exe`（PyInstaller onedir）；`YizhiStart.vbs` / Electron 优先使用该入口。回退：`build-installer.ps1 ...` 时给 `build-portable` 传 `-SkipBackendBinary`。

交叉链接：`docs/superpowers/plans/2026-07-15-yizhi-backend-binary.md`。

---

## Task 6: 端到端验收清单（必须人工/VM 执行）

- [ ] **Step 1: 干净 VM（无系统 Python）**

1. 安装 `Yizhi-Setup-x.y.z.exe`  
2. 桌面快捷方式 → **无控制台黑窗**  
3. splash → 主界面  
4. `%LOCALAPPDATA%\Yizhi\backend.log` 有 spawn 行且含 `yizhi-backend.exe`  
5. 提问 / 导入 PDF / 闪念保存冒烟  
6. 任务管理器无 `python.exe`（仅有 `yizhi-backend.exe` + `electron.exe`）——若仍保留 fallback python，允许短时 script，但健康稳态不应驻留解释器

- [ ] **Step 2: 回归开发机**

`YIZHI_DEV=1` / 源码树启动仍用系统 Python，`runtime\` 不存在时无回归。

- [ ] **Step 3: 体积与杀软**

记录 `runtime\` 目录大小；Windows Defender 首次扫描是否隔离。若隔离：签名或提交排除说明（不在本计划实现代码签名，但文档注明）。

---

## Task 7: Phase B — Nuitka（可选对照，同一契约）

**Files:**
- Create: `scripts/packaging/nuitka-backend.ps1`

- [ ] **Step 1: 脚本骨架**

```powershell
#Requires -Version 5.1
param([string]$OutDir = "")
$Root = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) { $OutDir = Join-Path $Root "dist\backend-runtime" }
# Requires: pip install nuitka ordered-set zstandard, and MSVC Build Tools
python -m nuitka `
  --standalone `
  --windows-console-mode=disable `
  --output-dir="$Root\dist\nuitka-out" `
  --output-filename=yizhi-backend.exe `
  --include-package=backend `
  --include-package=lib `
  --include-package=uvicorn `
  --include-package=fastapi `
  "$Root\backend\__frozen_main__.py"
# Then copy standalone tree → OutDir as runtime\ mirroring PyInstaller layout
```

- [ ] **Step 2: 验收**

同一套 Task 6；若 Nuitka 更稳且体积更优，再改 `build-backend-exe.ps1` 默认引擎为 Nuitka，**不得**改 VBS / main.js 契约。

**默认发版在 Phase B 验证通过前仍使用 PyInstaller。**

---

## 3. 风险与缓解

| 风险 | 缓解 |
|------|------|
| hiddenimport 漏模块 → 用户机秒退 | CI 冒烟 `/api/health`；保留 `-SkipBackendBinary` |
| 杀软误报 | onedir；后续 Ev 代码签名 |
| `MYK_ROOT` 下读 `lib` 源码仍可见 | 本阶段目标是「无解释器树 + 入口二进制」；完整源码仍可打进 asar/旁路。**可选下阶段**不随包装 `lib/*.py`，仅靠 `_internal`（需确认 frozen 已收录全部 lib） |
| GPL DocuBrowser | 二进制化不消除源码提供义务；更新 `GPL说明.md` 说明获取方式 |
| 路径含空格/`Program Files` | 已有引号 spawn；VBS `Chr(34)` 模式保持 |

---

## 4. 回滚预案

1. 构建：`build-portable.ps1 -ForInstaller -SkipBackendBinary`  
2. VBS / main.js 保持双轨探测，旧包无需立即升 VBS  
3. 若仅新包坏：Inno 上一版覆盖安装

---

## 5. 建议实施顺序（工期）

| 日 | 内容 |
|----|------|
| D1 | Task 1–2：入口 + PyInstaller 本机通过 `/api/health` |
| D2 | Task 3–4：main.js + VBS |
| D3 | Task 5：接入 installer；打出 Setup |
| D4 | Task 6：干净 VM 验收；修 hiddenimports |
| D5+ | Task 7（可选）Nuitka 对比 |

---

## 6. Self-Review（对照需求）

| 需求 | 对应任务 |
|------|----------|
| 写定 PyInstaller vs Nuitka | §0.1 + Task 7 |
| 与 YizhiStart.vbs 对接 | §0.2 + Task 4 |
| 与 Electron spawn 对接 | §0.3 + Task 3 |
| 接入现有安装包流水线 | Task 5–6 |
| 可回退 | §0.1 开关 + §4 |
| TDD | Task 1 |
| 无 TBD/模糊步骤 | 代码与命令已写全 |

**缺口（刻意延后）：** Electron asar 化、代码签名、完全去掉安装目录内 `lib/` 明文——单独立项，本计划不阻塞「后端 exe」交付。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-15-yizhi-backend-binary.md`.

**执行方式（需要落地写代码时任选其一）：**

1. **Subagent-Driven（推荐）** — 按 Task 派生子代理，任务间审查  
2. **Inline Execution** — 本会话按 `executing-plans` 连续执行  

本回合仅交付计划；收到「按该计划实施」后再动构建脚本与入口代码。
