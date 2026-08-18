#Requires -Version 5.1
<#
.SYNOPSIS
  构建易知 Windows 便携分发包（半自动安装包）

.DESCRIPTION
  产出 Yizhi-Portable/ 目录，内含**可搬迁**内置 Python（整份拷贝，非 venv）、预装 npm 依赖，
  用户无需全局 Python/Node。详见 docs/易知商业化实现方案.md 阶段 2。

  不会打包开发机 wiki 资料、上传文件、对话库；构建后初始化空知识库与空 SQLite。
  大模型配置从开发机 .env 注入 .env.user，设置页不显示（MYKNOWLEDGE_HIDE_LLM_SETTINGS=1）。

  重要：勿用 `python -m venv` 打包。venv 的 pyvenv.cfg 绑定开发机绝对路径，其它电脑会启动失败。

.PARAMETER OutputDir
  输出根目录，默认 dist/Yizhi-Portable

.PARAMETER LicenseServer
  注入 env.user.example → .env.user 的 MYKNOWLEDGE_LICENSE_SERVER

.PARAMETER JwtSecret
  注入 MYKNOWLEDGE_LICENSE_JWT_SECRET（须与 license-server 一致）

.PARAMETER EnvFile
  读取大模型/RAG 配置的源 .env，默认项目根 .env

.PARAMETER SkipTools
  跳过 setup_optional_tools / setup_docubrowser（加快构建）

.PARAMETER BackendBinary
  强制构建 runtime\yizhi-backend.exe（PyInstaller）

.PARAMETER SkipBackendBinary
  不构建后端二进制，仅用内置 python\（安装包回退）

.PARAMETER KeepBundledPythonFallback
  安装包默认在编好 runtime\yizhi-backend.exe 后删除重复的 python\（方案 A1）。
  加本开关则保留 python\ 作诊断便携包。

.EXAMPLE
  .\scripts\build-portable.ps1 -LicenseServer https://license.example.com -JwtSecret "your-jwt-secret"
#>
param(
    [string]$OutputDir = "",
    [string]$LicenseServer = "",
    [string]$JwtSecret = "",
    [string]$EnvFile = "",
    [string]$UpdateBaseUrl = "",
    [switch]$SkipTools,
    [switch]$SkipDocubrowser,
    [switch]$ForInstaller,
    [switch]$BackendBinary,
    [switch]$SkipBackendBinary,
    [switch]$KeepBundledPythonFallback
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $OutputDir) {
    $ver = (Get-Content (Join-Path $Root "electron\package.json") -Raw | ConvertFrom-Json).version
    $OutputDir = Join-Path $Root "dist\Yizhi-Portable-$ver"
} else {
    $ver = (Get-Content (Join-Path $Root "electron\package.json") -Raw | ConvertFrom-Json).version
}
if (-not $UpdateBaseUrl -and $LicenseServer -match "yzwhysxx\.cn") {
    $UpdateBaseUrl = "https://www.yzwhysxx.cn/yizhi"
}
if (-not $EnvFile) {
    $EnvFile = Join-Path $Root ".env"
}

# 从开发机 .env 注入到用户包的键（勿含 EXTRA_DIRS、授权密钥等）
$BundledEnvKeys = @(
    "MYKNOWLEDGE_LLM_API_BASE",
    "MYKNOWLEDGE_LLM_API_KEY",
    "MYKNOWLEDGE_LLM_MODEL",
    "MYKNOWLEDGE_LLM_TEMPERATURE_ASK",
    "MYKNOWLEDGE_LLM_TEMPERATURE_PRODUCE",
    "MYKNOWLEDGE_LLM_MAX_TOKENS_PRODUCE",
    "MYKNOWLEDGE_RAG_MODE",
    "MYKNOWLEDGE_RAG_TOP_ASK",
    "MYKNOWLEDGE_RAG_TOP_PRODUCE",
    "MYKNOWLEDGE_RAG_HYBRID_KEYWORD",
    "MYKNOWLEDGE_RAG_HYBRID_VECTOR",
    "MYKNOWLEDGE_EMBEDDING_MODEL",
    "MYKNOWLEDGE_RERANK",
    "MYKNOWLEDGE_RERANK_MODEL",
    "MYKNOWLEDGE_RERANK_URL",
    "MYKNOWLEDGE_UPDATE_URL"
)

function Read-DotEnvMap([string]$Path) {
    $map = @{}
    if (-not (Test-Path $Path)) { return $map }
    Get-Content $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $eq = $line.IndexOf("=")
        if ($eq -lt 1) { return }
        $key = $line.Substring(0, $eq).Trim()
        $val = $line.Substring($eq + 1).Trim()
        if ($val -match '^["''](.+)["'']$') { $val = $Matches[1] }
        if ($key) { $map[$key] = $val }
    }
    return $map
}

function Merge-EnvText([string]$Text, [hashtable]$Updates) {
    $lines = if ($Text) { $Text -split "`r?`n" } else { @() }
    $out = New-Object System.Collections.Generic.List[string]
    $seen = @{}
    foreach ($line in $lines) {
        $trim = $line.Trim()
        if ($trim -and -not $trim.StartsWith("#") -and $trim.Contains("=")) {
            $key = $trim.Split("=", 2)[0].Trim()
            if ($Updates.ContainsKey($key)) {
                $out.Add("$key=$($Updates[$key])")
                $seen[$key] = $true
                continue
            }
        }
        $out.Add($line)
    }
    foreach ($key in $Updates.Keys) {
        if (-not $seen.ContainsKey($key)) {
            $out.Add("$key=$($Updates[$key])")
        }
    }
    return ($out -join "`n").TrimEnd() + "`n"
}

function Resolve-BundledPythonExe([string]$PyDir) {
    foreach ($rel in @("python.exe", "Scripts\python.exe")) {
        $p = Join-Path $PyDir $rel
        if (Test-Path $p) { return $p }
    }
    return ""
}

function Assert-PythonRelocatable([string]$PyDir, [string]$PyExe) {
    $cfg = Join-Path $PyDir "pyvenv.cfg"
    if (Test-Path $cfg) {
        $raw = Get-Content $cfg -Raw -ErrorAction SilentlyContinue
        if ($raw -match '(?i)Users\\|Program Files|:\\') {
            throw "内置 Python 含绝对路径 pyvenv.cfg（不可搬迁），请勿使用 venv 打包。文件: $cfg"
        }
        throw "内置 Python 仍存在 pyvenv.cfg，换机可能失败。请使用整份 Python 拷贝。文件: $cfg"
    }
    # 临时 .py + Continue：避免 -c here-string 与 stderr→ErrorRecord 在 Stop 下误杀
    $probePy = Join-Path $env:TEMP ("yizhi-assert-python-{0}.py" -f [guid]::NewGuid().ToString("N"))
    $pyCode = @"
import os, sys
py_dir = os.environ["YIZHI_ASSERT_PYDIR"]
site = os.path.normcase(os.path.abspath(os.path.join(py_dir, "Lib", "site-packages")))
paths = [os.path.normcase(os.path.abspath(p)) for p in sys.path if p]
if site not in paths:
    raise SystemExit("site-packages not on sys.path: " + site + " | " + repr(sys.path))
joined = "\n".join(paths).lower()
if "\\users\\" in joined and "\\programs\\python" in joined:
    raise SystemExit("sys.path still points at machine Python: " + repr(sys.path))
import anyio, fastapi, uvicorn
print(sys.prefix)
"@
    $prevEa = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $env:YIZHI_ASSERT_PYDIR = $PyDir
    try {
        [System.IO.File]::WriteAllText($probePy, $pyCode, (New-Object System.Text.UTF8Encoding $false))
        $probe = & $PyExe $probePy 2>&1 | Out-String
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prevEa
        Remove-Item Env:YIZHI_ASSERT_PYDIR -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $probePy -Force -ErrorAction SilentlyContinue
    }
    if ($code -ne 0) {
        throw "内置 Python 自检失败: $probe"
    }
    Write-Host "内置 Python 可搬迁自检通过: $PyExe"
}

function Invoke-NativeLogged {
    # Native stderr becomes ErrorRecord under $ErrorActionPreference=Stop; keep exit-code check only.
    param([scriptblock]$Script)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $lines = & $Script 2>&1
        $code = $LASTEXITCODE
        foreach ($line in $lines) { Write-Host "$line" }
        return $code
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Install-BundledPython([string]$PyDir, [string]$RequirementsFile) {
    <#
      将当前构建机的「基础 Python」拷到打包目录（可搬迁）。
      不用 venv；且必须排除开发机 Lib\site-packages（常达数 GB），否则会假死数小时。
    #>
    Write-Host "创建可搬迁内置 Python（拷贝 base_prefix，跳过 site-packages）…"
    if (Test-Path $PyDir) {
        Write-Host "  清理旧目录 $PyDir …"
        Remove-Item -LiteralPath $PyDir -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path $PyDir) {
            throw "无法清理旧 python 目录: $PyDir （请结束 Robocopy/杀毒占用后重试）"
        }
    }

    $basePrefix = (& python -c "import sys; print(sys.base_prefix)").Trim()
    if (-not $basePrefix -or -not (Test-Path (Join-Path $basePrefix "python.exe"))) {
        throw "无法解析构建机 Python base_prefix（需系统安装的 Python，而非已损坏的 venv）"
    }
    Write-Host "  源: $basePrefix"
    Write-Host "  目标: $PyDir"
    Write-Host "  （最小标准库：排除 site-packages / Tcl-Tk / idle / 测试与头文件；约 1～3 分钟）"

    New-Item -ItemType Directory -Path $PyDir -Force | Out-Null
    # /XD site-packages：避免拷贝开发机全局包（torch 等可达数 GB）
    # Tcl/Tk、idle、include 等仅开发或 GUI 脚本用，安装包 Electron 不依赖
    # 外部命令必须 Out-Host：Write-Host/管道仍可能进函数成功流，污染调用方变量
    & robocopy $basePrefix $PyDir /E /MT:16 /R:1 /W:1 `
        /XD Doc Docs __pycache__ site-packages test tests `
           tcl tk idlelib turtledemo tkinter include libs Libs `
        /XF *.pdb *.lib *.exp *.pyc *.a `
        /NFL /NDL /NJH /nc /ns | Out-Host
    $rc = $LASTEXITCODE
    if ($rc -ge 8) {
        throw "robocopy 复制 Python 失败，退出码 $rc"
    }
    Write-Host "  robocopy 完成（码 $rc，0-7 均为成功）"

    $cfg = Join-Path $PyDir "pyvenv.cfg"
    if (Test-Path $cfg) { Remove-Item $cfg -Force }

    $site = Join-Path $PyDir "Lib\site-packages"
    New-Item -ItemType Directory -Path $site -Force | Out-Null

    $PyExe = Resolve-BundledPythonExe $PyDir
    if (-not $PyExe) {
        throw "复制后未找到 python.exe: $PyDir"
    }

    Write-Host "  ensurepip + pip install（仅 requirements-runtime.txt；下载时可能静默数分钟，勿中断）…"
    $pipArgs = @("--disable-pip-version-check", "--no-warn-script-location", "--progress-bar", "on")
    $ec = Invoke-NativeLogged { & $PyExe -m ensurepip --upgrade }
    if ($ec -ne 0) {
        Write-Warning "ensurepip 失败，尝试 get-pip…"
        $getPip = Join-Path $env:TEMP "yizhi-get-pip.py"
        Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip -UseBasicParsing
        $ec = Invoke-NativeLogged { & $PyExe $getPip }
        if ($ec -ne 0) { throw "get-pip 失败" }
    }
    Write-Host "  升级 pip/wheel…"
    $ec = Invoke-NativeLogged { & $PyExe -m pip install @pipArgs --upgrade pip wheel }
    if ($ec -ne 0) { throw "升级 pip 失败" }
    Write-Host "  安装 runtime 依赖: $RequirementsFile"
    $ec = Invoke-NativeLogged { & $PyExe -m pip install @pipArgs -r $RequirementsFile }
    if ($ec -ne 0) { throw "pip install -r requirements-runtime.txt 失败" }
    Write-Host "  pip install 完成"

    # 装完依赖后卸掉装包工具，减小体积（运行时不再需要 pip）
    [void](Invoke-NativeLogged { & $PyExe -m pip uninstall -y pip setuptools wheel })
    foreach ($dropPy in @(
        "Lib\ensurepip",
        "Lib\venv",
        "Scripts\pip.exe", "Scripts\pip3.exe", "Scripts\pip3.13.exe",
        "Scripts\pip3.12.exe", "Scripts\pip3.11.exe", "Scripts\pip3.10.exe"
    )) {
        $dp = Join-Path $PyDir $dropPy
        if (Test-Path $dp) {
            Remove-Item -LiteralPath $dp -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    Assert-PythonRelocatable -PyDir $PyDir -PyExe $PyExe
    # 故意无 return：调用方只用 Resolve-BundledPythonExe，避免任何输出污染 $PyExe
}

Write-Host "=== 易知便携包构建 ===" -ForegroundColor Cyan
Write-Host "源目录: $Root"
Write-Host "输出:   $OutputDir"

# --- 1. 复制应用文件（排除开发机 wiki / 上传 / 对话库）---
$ExcludeDirs = @(
    ".git", "dist", "license-server", "node_modules", ".venv", "venv",
    ".ruff_cache", ".pytest_cache", "tests",
    "__pycache__", ".docubrowser", ".rag", ".memory", ".license", ".loop", ".config",
    "inbox", "sources", "notes", "entities", "concepts", "comparisons", "index",
    "archive", "output", "assets"
)
if ($ForInstaller) {
    # 保留 skills/：GUI「工作流」内置卡片由 lib/workflows.py 从项目 skills 发现
    $ExcludeDirs += @("docs", "design-md", ".cursor", ".agents", ".specify", "specs")
}
$ExcludeFiles = @(
    ".env", "license.db", "STATE.md", "LOOP.md", "purpose.md", ".wiki-cache.json"
)

function Should-SkipPath([string]$Rel) {
    foreach ($d in $ExcludeDirs) {
        if ($Rel -eq $d -or $Rel.StartsWith("$d\")) { return $true }
    }
    if ($ForInstaller -and ($Rel -eq "scripts\installer" -or $Rel.StartsWith("scripts\installer\"))) {
        return $true
    }
    $leaf = Split-Path -Leaf $Rel
    if ($ExcludeFiles -contains $leaf) { return $true }
    return $false
}

function Stop-ProcessesUnderPath([string]$RootPath) {
    if (-not $RootPath) { return }
    $rootNorm = $RootPath.TrimEnd('\')
    try {
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | ForEach-Object {
            if ($_.ProcessId -eq $PID) { return }
            $name = $_.Name
            $ep = $_.ExecutablePath
            $cl = $_.CommandLine
            $isApp = $name -match '^(electron|python|pythonw|node)\.exe$'
            $hit = $false
            if ($ep -and $ep.StartsWith($rootNorm, [StringComparison]::OrdinalIgnoreCase)) {
                $hit = $true
            } elseif ($isApp -and $cl -and $cl.IndexOf($rootNorm, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                # 仅杀应用进程，避免误杀命令行里含该路径的 powershell/build 脚本
                $hit = $true
            }
            if (-not $hit) { return }
            Write-Host "  结束占用进程 PID=$($_.ProcessId) $name"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    } catch {
        # ignore enumeration errors
    }
    Get-Process -Name electron -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            if ($_.Id -eq $PID) { return }
            if ($_.Path -and $_.Path.StartsWith($rootNorm, [StringComparison]::OrdinalIgnoreCase)) {
                Write-Host "  结束 Electron PID=$($_.Id)"
                Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
            }
        } catch {
            # ignore
        }
    }
}

function Remove-DirectoryRobust {
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [int]$MaxAttempts = 5,
        [int]$DelayMs = 800
    )
    if (-not (Test-Path -LiteralPath $Path)) { return $true }

    Stop-ProcessesUnderPath $Path
    Start-Sleep -Milliseconds 500

    for ($i = 1; $i -le $MaxAttempts; $i++) {
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            return $true
        } catch {
            if ($i -eq $MaxAttempts) { break }
            Write-Host "  目录被占用，${DelayMs}ms 后重试 ($i/$MaxAttempts)…"
            Stop-ProcessesUnderPath $Path
            Start-Sleep -Milliseconds $DelayMs
        }
    }

    $stamp = Get-Date -Format "yyyyMMddHHmmss"
    $archiveName = "$(Split-Path -Leaf $Path).old-$stamp"
    Write-Host "  无法删除，改名为 $archiveName 后继续（可稍后手动清理）…"
    try {
        Rename-Item -LiteralPath $Path -NewName $archiveName -ErrorAction Stop
        return $true
    } catch {
        Write-Warning "无法清理或重命名: $Path — $($_.Exception.Message)"
        return $false
    }
}

if (Test-Path $OutputDir) {
    Write-Host "清理旧输出…"
    $cleaned = Remove-DirectoryRobust -Path $OutputDir
    if (-not $cleaned) {
        $stamp = Get-Date -Format "yyyyMMddHHmmss"
        $alt = "$OutputDir-$stamp"
        Write-Warning "旧 staging 仍被占用，改为输出到: $alt"
        Write-Warning "请关闭仍在运行的易知（含从 dist\\Yizhi-Staging 启动的实例），稍后删除旧目录。"
        $OutputDir = $alt
    }
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
# 供 build-installer 对齐实际输出路径（旧目录被锁时会落到带时间戳的备用目录）
$distRoot = Join-Path $Root "dist"
if (-not (Test-Path -LiteralPath $distRoot)) {
    New-Item -ItemType Directory -Path $distRoot -Force | Out-Null
}
[System.IO.File]::WriteAllText((Join-Path $distRoot ".yizhi-last-output.txt"), $OutputDir)
Write-Host "YIZHI_OUTPUT_DIR=$OutputDir"

Write-Host "复制应用文件（不含测试知识库与上传资料）…"
Get-ChildItem -Path $Root -Force | ForEach-Object {
    $name = $_.Name
    if (Should-SkipPath $name) { return }
    $dest = Join-Path $OutputDir $name
    if ($_.PSIsContainer) {
        if ($name -eq "electron") {
            New-Item -ItemType Directory -Path $dest -Force | Out-Null
            # 不复制 node_modules，避免占用与开发机路径污染；后续 npm install 重装
            & robocopy $_.FullName $dest /E /XD node_modules /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
            if ($LASTEXITCODE -ge 8) { throw "复制 electron 失败 (robocopy exit $LASTEXITCODE)" }
        } else {
            Copy-Item -Path $_.FullName -Destination $dest -Recurse -Force
        }
    } else {
        Copy-Item -Path $_.FullName -Destination $dest -Force
    }
}

# 产品自我介绍：docs 整树在安装包中排除；固化宣传文案 → prompts/
New-Item -ItemType Directory -Path (Join-Path $OutputDir "prompts") -Force | Out-Null
$ProductDir = Join-Path $OutputDir "product"
New-Item -ItemType Directory -Path $ProductDir -Force | Out-Null
$YizhiPromoMd = Join-Path $Root "docs\product\yizhi-promo.md"
$YizhiPromoDst = Join-Path $OutputDir "prompts\yizhi-product.md"
if (Test-Path -LiteralPath $YizhiPromoMd) {
    Copy-Item -LiteralPath $YizhiPromoMd -Destination $YizhiPromoDst -Force
    Write-Host "已固化宣传文案说明 → prompts\yizhi-product.md"
} elseif (Test-Path -LiteralPath (Join-Path $Root "prompts\yizhi-product.md")) {
    Copy-Item -LiteralPath (Join-Path $Root "prompts\yizhi-product.md") -Destination $YizhiPromoDst -Force
    Write-Host "已固化 prompts\yizhi-product.md"
} else {
    Write-Warning "缺少 docs\product\yizhi-promo.md，安装包自我介绍能力不完整"
}
$YizhiDocx = Join-Path $Root "docs\易知-自我进化个人知识库-宣传文案.docx"
if (Test-Path -LiteralPath $YizhiDocx) {
    Copy-Item -LiteralPath $YizhiDocx -Destination (Join-Path $ProductDir "易知-自我进化个人知识库-宣传文案.docx") -Force
    Copy-Item -LiteralPath $YizhiDocx -Destination (Join-Path $OutputDir "prompts\易知-自我进化个人知识库-宣传文案.docx") -Force
    Write-Host "已打包宣传文案.docx → product\ 与 prompts\"
} else {
    Write-Warning "缺少 docs\易知-自我进化个人知识库-宣传文案.docx"
}
$SelfIntroMp3 = Join-Path $Root "electron\assets\audio\yizhi-self-intro.mp3"
if (Test-Path -LiteralPath $SelfIntroMp3) {
    $audioDst = Join-Path $OutputDir "electron\assets\audio"
    New-Item -ItemType Directory -Path $audioDst -Force | Out-Null
    Copy-Item -LiteralPath $SelfIntroMp3 -Destination (Join-Path $audioDst "yizhi-self-intro.mp3") -Force
    Copy-Item -LiteralPath $SelfIntroMp3 -Destination (Join-Path $ProductDir "yizhi-self-intro.mp3") -Force
    Write-Host "已打包自我介绍音频 → electron\assets\audio\yizhi-self-intro.mp3"
} else {
    Write-Warning "缺少 electron\assets\audio\yizhi-self-intro.mp3（关于页「自我介绍」将无法播放）"
}

# 若旧 staging 残留 node_modules，带重试删除
$ElectronDir = Join-Path $OutputDir "electron"
if (Test-Path (Join-Path $ElectronDir "node_modules")) {
    Remove-DirectoryRobust -Path (Join-Path $ElectronDir "node_modules")
}

# --- 2. 内置可搬迁 Python（整份拷贝，禁止 venv；仅 runtime 依赖）---
$PyDir = Join-Path $OutputDir "python"
$reqFile = Join-Path $Root "requirements-runtime.txt"
if (-not (Test-Path $reqFile)) {
    $reqFile = Join-Path $OutputDir "requirements-runtime.txt"
}
if (-not (Test-Path $reqFile)) {
    throw "缺少 requirements-runtime.txt（安装包仅允许最小运行时依赖）"
}
$null = Install-BundledPython -PyDir $PyDir -RequirementsFile $reqFile
# 路径只从磁盘解析，绝不信函数返回值（pip 日志极易污染赋值）
$PyExe = Resolve-BundledPythonExe $PyDir
if (-not $PyExe -or -not (Test-Path -LiteralPath $PyExe)) {
    throw "内置 Python 未就绪: $PyDir\python.exe"
}
Write-Host "内置 Python: $PyExe"

# --- 2b. 安装包默认再构建 runtime\yizhi-backend.exe（PyInstaller）---
# 构建期仍需 python\（setup_optional_tools / init）；A1 在 prune 阶段删除重复 python\
$useBackendBinary = $false
if ($BackendBinary) { $useBackendBinary = $true }
elseif ($ForInstaller -and -not $SkipBackendBinary) { $useBackendBinary = $true }

# 安装包 + 已编二进制：默认去掉 python\；诊断包用 -KeepBundledPythonFallback
$removeBundledPython = $false
if ($ForInstaller -and $useBackendBinary -and -not $KeepBundledPythonFallback) {
    $removeBundledPython = $true
}

if ($useBackendBinary) {
    Write-Host "构建后端二进制 runtime\yizhi-backend.exe …" -ForegroundColor Cyan
    $runtimeDir = Join-Path $OutputDir "runtime"
    & (Join-Path $PSScriptRoot "build-backend-exe.ps1") -OutDir $runtimeDir -Clean
    if ($LASTEXITCODE -ne 0) { throw "build-backend-exe 失败" }
    $frozenExe = Join-Path $runtimeDir "yizhi-backend.exe"
    if (-not (Test-Path -LiteralPath $frozenExe)) {
        throw "缺少 $frozenExe"
    }
    Write-Host "后端二进制就绪: $frozenExe"
    if ($removeBundledPython) {
        Write-Host "安装包将在精简阶段删除重复 python\（仅保留 runtime\）" -ForegroundColor Cyan
    }
} else {
    Write-Host "跳过后端二进制（将使用 python\python.exe -m backend）" -ForegroundColor Yellow
}

# --- 3. Electron：装依赖 → 同步到 vendor → 再删掉非 electron 的 node_modules ---
Write-Host "npm install (electron)…"
Push-Location $ElectronDir
npm install --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "npm install 失败" }
npm run build
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "electron vendor sync 失败" }
# vendor 已同步 toastui/d3/file-viewer/marked；删掉构建期 npm 包，仅留 electron
Write-Host "精简 electron/node_modules（删除已同步到 vendor 的包）…"
& (Join-Path $PSScriptRoot "prune_electron_modules.ps1") -ElectronDir $ElectronDir
Pop-Location

# --- 4. 可选工具与 DocuBrowser ---
if (-not $SkipTools) {
    Write-Host "安装可选工具 (ffmpeg/bun/yt-dlp)…"
    Push-Location $OutputDir
    try {
        & $PyExe "scripts\setup_optional_tools.py"
        if ($LASTEXITCODE -ne 0) { throw "setup_optional_tools 失败 (exit $LASTEXITCODE)" }
    } finally {
        Pop-Location
    }
    $ytdlpExe = Join-Path $OutputDir "third_party\yt-dlp\yt-dlp.exe"
    if (-not (Test-Path -LiteralPath $ytdlpExe)) {
        throw "缺少 $ytdlpExe（B 站字幕入库依赖）。请在开发机运行: python scripts/setup_optional_tools.py，或设置 MYKNOWLEDGE_YTDLP_PATH 后重试构建。"
    }
    Write-Host "yt-dlp 已打包: $ytdlpExe"
    $bunExe = Join-Path $OutputDir "third_party\bun\bun.exe"
    if (-not (Test-Path -LiteralPath $bunExe)) {
        throw "缺少 $bunExe（网页/公众号增强抓取依赖）。请运行: python scripts/setup_optional_tools.py 后重试构建。"
    }
    Write-Host "bun 已打包: $bunExe"
    $ffmpegBin = Join-Path $OutputDir "third_party\ffmpeg\bin"
    $ffmpegExe = Join-Path $ffmpegBin "ffmpeg.exe"
    if (-not (Test-Path -LiteralPath $ffmpegExe)) {
        throw "缺少 $ffmpegExe（播客合并/音视频依赖）。请将完整 ffmpeg\bin（含 av*.dll）放入 third_party，或重跑 setup_optional_tools.py。"
    }
    $ffmpegDlls = @(Get-ChildItem -LiteralPath $ffmpegBin -Filter "*.dll" -ErrorAction SilentlyContinue)
    if ($ffmpegDlls.Count -lt 5) {
        throw "ffmpeg bin 内 DLL 过少（$($ffmpegDlls.Count)），仅拷 exe 会导致用户机闪退。请拷贝完整 bin（含 avcodec 等）。"
    }
    $ffOut = & $ffmpegExe -hide_banner -version 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0 -or ($ffOut -notmatch "(?i)ffmpeg")) {
        throw "打包内 ffmpeg 无法运行 -version（缺 DLL 或损坏）: $ffmpegExe"
    }
    Write-Host "ffmpeg 已打包: $ffmpegExe ($($ffmpegDlls.Count) DLLs)"
}

# 安装包无论是否 -SkipTools，都必须带走可运行的 ffmpeg（播客完整音频）
if ($ForInstaller) {
    $ffmpegExeReq = Join-Path $OutputDir "third_party\ffmpeg\bin\ffmpeg.exe"
    $ffmpegBinReq = Join-Path $OutputDir "third_party\ffmpeg\bin"
    if (-not (Test-Path -LiteralPath $ffmpegExeReq)) {
        $srcFf = Join-Path $Root "third_party\ffmpeg\bin"
        if (Test-Path (Join-Path $srcFf "ffmpeg.exe")) {
            New-Item -ItemType Directory -Path $ffmpegBinReq -Force | Out-Null
            Copy-Item -Path (Join-Path $srcFf "*") -Destination $ffmpegBinReq -Force
            Write-Host "已从开发树补拷 ffmpeg -> $ffmpegBinReq"
        }
    }
    if (-not (Test-Path -LiteralPath $ffmpegExeReq)) {
        throw "ForInstaller 缺少 $ffmpegExeReq。请先在仓库 third_party/ffmpeg/bin 放入完整 ffmpeg（exe+DLL）。"
    }
    $dllN = @(Get-ChildItem -LiteralPath $ffmpegBinReq -Filter "*.dll" -ErrorAction SilentlyContinue).Count
    if ($dllN -lt 5) {
        throw "ForInstaller：ffmpeg DLL 不足（$dllN）。用户机播客合并会失败。"
    }
}
if (-not $SkipDocubrowser) {
    Write-Host "setup_docubrowser…"
    Push-Location $OutputDir
    try {
        & $PyExe "scripts\setup_docubrowser.py"
        if ($LASTEXITCODE -ne 0) { throw "setup_docubrowser 失败 (exit $LASTEXITCODE)" }
    } finally {
        Pop-Location
    }
}

# --- 5. 初始化空知识库与空 SQLite（不携带开发机数据）---
Write-Host "初始化空知识库与空数据库…"
$env:WIKI_ROOT = $OutputDir
$env:MYKNOWLEDGE_ROOT = $OutputDir
Push-Location $OutputDir
try {
    & $PyExe "scripts\init_wiki.py" --root $OutputDir
    if ($LASTEXITCODE -ne 0) { throw "init_wiki 失败" }
} finally {
    Pop-Location
    Remove-Item Env:WIKI_ROOT -ErrorAction SilentlyContinue
    Remove-Item Env:MYKNOWLEDGE_ROOT -ErrorAction SilentlyContinue
}

# --- 6. 用户 .env（注入大模型 + 订阅，设置页隐藏 LLM）---
$EnvUserSrc = Join-Path $OutputDir "env.user.example"
$EnvUserDst = Join-Path $OutputDir ".env.user"
if (-not (Test-Path $EnvUserSrc)) {
    Copy-Item (Join-Path $Root "env.user.example") $EnvUserSrc -Force
}
$envText = Get-Content $EnvUserSrc -Raw -Encoding UTF8
$envUpdates = @{ "MYKNOWLEDGE_HIDE_LLM_SETTINGS" = "1" }

if ($LicenseServer) {
    $envUpdates["MYKNOWLEDGE_LICENSE_SERVER"] = $LicenseServer
}
if ($JwtSecret) {
    $envUpdates["MYKNOWLEDGE_LICENSE_JWT_SECRET"] = $JwtSecret
}
if ($UpdateBaseUrl) {
    $updateUrl = if ($UpdateBaseUrl.EndsWith("latest.json")) { $UpdateBaseUrl } else { "{0}/latest.json" -f $UpdateBaseUrl.TrimEnd('/') }
    $envUpdates["MYKNOWLEDGE_UPDATE_URL"] = $updateUrl
}

$devEnv = Read-DotEnvMap $EnvFile
foreach ($key in $BundledEnvKeys) {
    if ($devEnv.ContainsKey($key) -and $devEnv[$key]) {
        $envUpdates[$key] = $devEnv[$key]
    }
}
if (-not $envUpdates.ContainsKey("MYKNOWLEDGE_LLM_API_BASE")) {
    Write-Warning "未在 $EnvFile 找到 MYKNOWLEDGE_LLM_API_BASE，用户包大模型可能未配置"
}

$envText = Merge-EnvText $envText $envUpdates
[System.IO.File]::WriteAllText($EnvUserDst, $envText, [System.Text.UTF8Encoding]::new($false))
Write-Host "已写入 .env.user（大模型已注入，设置页隐藏）"

# --- 7. 便携/安装启动器 ---
$PortableFlags = @(
    'set "YIZHI_PORTABLE=1"',
    'set "PATH=%MYK_ROOT%\python;%MYK_ROOT%\python\Scripts;%MYK_ROOT%\third_party\ffmpeg\bin;%MYK_ROOT%\third_party\bun;%MYK_ROOT%\third_party\yt-dlp;%PATH%"'
)
if ($ForInstaller) {
    $PortableFlags = @('set "YIZHI_INSTALLED=1"') + $PortableFlags
}
# IMPORTANT: avoid "if (...) (" blocks with echo text containing "()".
# cmd parses the whole block and treats echo "(or copy...)" as syntax →
# ". was unexpected at this time." → black window flash, Electron never starts.
$Launcher = @"
@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
set "MYK_ROOT=%~dp0"
set "MYK_ROOT=%MYK_ROOT:~0,-1%"
set "PYTHONIOENCODING=utf-8"
set "YIZHI_DATA=%LOCALAPPDATA%\Yizhi"
if not exist "%YIZHI_DATA%" mkdir "%YIZHI_DATA%" >nul 2>&1
>>"%YIZHI_DATA%\launcher.log" echo %date% %time% bat start MYK_ROOT=%MYK_ROOT%
$($PortableFlags -join "`n")

set "PATH=%MYK_ROOT%\python;%MYK_ROOT%\python\Scripts;%MYK_ROOT%\third_party\ffmpeg\bin;%MYK_ROOT%\third_party\bun;%MYK_ROOT%\third_party\yt-dlp;%PATH%"
set "WIKI_ROOT=%YIZHI_DATA%"
set "MYKNOWLEDGE_ROOT=%YIZHI_DATA%"
set "MYK_ROOT=%MYK_ROOT%"

set "PY_EXE=%MYK_ROOT%\python\python.exe"
if not exist "%PY_EXE%" set "PY_EXE=%MYK_ROOT%\python\Scripts\python.exe"
set "EL_EXE=%MYK_ROOT%\electron\node_modules\electron\dist\electron.exe"
set "EL_DIR=%MYK_ROOT%\electron"
set "EL_ASAR=%EL_DIR%\node_modules\electron\dist\resources\default_app.asar"

if not exist "%PY_EXE%" goto :fail_python
if not exist "%EL_EXE%" goto :fail_electron
if not exist "%EL_ASAR%" goto :fail_asar

>>"%YIZHI_DATA%\launcher.log" echo launch %EL_EXE% cwd=%EL_DIR%
cd /d "%EL_DIR%"
if errorlevel 1 goto :fail_cd

rem MUST use empty title "". start "Yizhi" ... is treated as UNC \\yizhi
start "" /D "%EL_DIR%" "%EL_EXE%" .
ping -n 4 127.0.0.1 >nul
wmic process where "name='electron.exe' and ExecutablePath like '%%Yizhi%%electron%%'" get ProcessId 2>nul | findstr /R "[0-9]" >nul
if not errorlevel 1 goto :ok

>>"%YIZHI_DATA%\launcher.log" echo FAIL electron exited; foreground retry
echo [Yizhi] Electron exited immediately.
echo Check: %EL_ASAR%
echo Often missing VC++ - run: %MYK_ROOT%\redist\vc_redist.x64.exe
echo Log: %YIZHI_DATA%\launcher.log
echo.
echo Retrying in this window - errors will stay visible...
"%EL_EXE%" .
echo Electron exit code=%ERRORLEVEL%
pause
exit /b 1

:ok
>>"%YIZHI_DATA%\launcher.log" echo OK electron running
exit /b 0

:fail_python
>>"%YIZHI_DATA%\launcher.log" echo FAIL python missing
echo [Yizhi] Missing Python: %MYK_ROOT%\python\python.exe
echo Reinstall the full package.
pause
exit /b 1

:fail_electron
>>"%YIZHI_DATA%\launcher.log" echo FAIL electron missing
echo [Yizhi] Missing Electron: %EL_EXE%
echo Reinstall the full package.
pause
exit /b 1

:fail_asar
>>"%YIZHI_DATA%\launcher.log" echo FAIL missing default_app.asar
echo [Yizhi] Missing electron resources\default_app.asar
echo Reinstall the full package.
pause
exit /b 1

:fail_cd
>>"%YIZHI_DATA%\launcher.log" echo FAIL cannot cd EL_DIR
echo [Yizhi] Cannot cd to %EL_DIR%
pause
exit /b 1
"@
if ($ForInstaller) {
    # 安装版：真正静默入口是 YizhiStart.vbs；bat 仅薄封装（勿在此直接起 Electron，否则必出黑窗）
    $thinBat = @"
@echo off
setlocal EnableExtensions
rem Prefer start so this cmd exits immediately if user double-clicks the .bat
start "" wscript.exe "%~dp0YizhiStart.vbs"
exit /b 0
"@
    [System.IO.File]::WriteAllText((Join-Path $OutputDir "YizhiStart.bat"), $thinBat, [System.Text.UTF8Encoding]::new($false))
    $VbsSrc = Join-Path $Root "scripts\installer\YizhiStart.vbs"
    $VbsDst = Join-Path $OutputDir "YizhiStart.vbs"
    $vbsText = [System.IO.File]::ReadAllText($VbsSrc)
    if ($vbsText -match '[^\x09\x0A\x0D\x20-\x7E]') {
        throw "YizhiStart.vbs must be ASCII-only (wscript.exe cannot compile UTF-8 CJK): $VbsSrc"
    }
    [System.IO.File]::WriteAllText($VbsDst, $vbsText, [System.Text.ASCIIEncoding]::new())
} else {
    [System.IO.File]::WriteAllText((Join-Path $OutputDir "启动易知.bat"), $Launcher, [System.Text.UTF8Encoding]::new($false))
}

# --- 8. README ---
if ($ForInstaller) {
    $Readme = @"
易知 安装版
==========

1. 从开始菜单或桌面快捷方式启动「易知」（或运行 YizhiStart.bat）
2. 用户数据（笔记、授权、配置）保存在 %LOCALAPPDATA%\Yizhi
3. 首次运行会自动从 .env.user 生成 .env（大模型已预配置，无需在设置中填写）
4. 未订阅时会提示激活；购买与激活说明见 https://www.yzwhysxx.cn/yizhi/purchase.html

升级：运行新版安装包覆盖安装；用户数据保留在 %LOCALAPPDATA%\Yizhi
卸载：控制面板 → 卸载程序 → 易知（用户笔记保留在 %LOCALAPPDATA%\Yizhi，可手动备份）

GPL 组件说明：GPL说明.md
"@
} else {
    $Readme = @"
易知 便携版
==========

1. 双击「启动易知.bat」
2. 首次运行会自动从 .env.user 生成 .env（大模型已预配置，无需在设置中填写）
3. 未订阅时会提示激活；详见 docs/commercial/购买与激活指南.md

升级：解压新版本覆盖同目录，保留 wiki 与 .env

GPL 组件说明：docs/commercial/GPL说明.md
"@
}
[System.IO.File]::WriteAllText((Join-Path $OutputDir "README.txt"), $Readme, [System.Text.UTF8Encoding]::new($false))

# --- 9. 复制 GPL 说明到根 ---
$GplSrc = Join-Path $Root "docs\commercial\GPL说明.md"
if (Test-Path $GplSrc) {
    Copy-Item $GplSrc (Join-Path $OutputDir "GPL说明.md") -Force
}

# --- 10. 复制在线购买页 + 更新清单（可部署到 www.yzwhysxx.cn/yizhi/）---
$yizhiWebSrc = Join-Path $Root "docs\commercial\yizhi-web"
$yizhiWebDst = Join-Path $OutputDir "yizhi-web"
New-Item -ItemType Directory -Path $yizhiWebDst -Force | Out-Null
foreach ($html in @("purchase.html", "faq.html", "changelog.html")) {
    $src = Join-Path $Root "docs\commercial\$html"
    if (Test-Path $src) {
        Copy-Item $src (Join-Path $yizhiWebDst $html) -Force
    }
}
if ($UpdateBaseUrl) {
    $base = $UpdateBaseUrl.TrimEnd('/')
    $latest = @"
{
  "latest_version": "$ver",
  "download_url": "$base/Yizhi-Setup-$ver.zip",
  "release_notes": "易知 $ver"
}
"@
    [System.IO.File]::WriteAllText((Join-Path $yizhiWebDst "latest.json"), $latest.Trim(), [System.Text.UTF8Encoding]::new($false))
    $yizhiWebPublish = Join-Path $Root "docs\commercial\yizhi-web"
    New-Item -ItemType Directory -Path $yizhiWebPublish -Force | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $yizhiWebPublish "latest.json"), $latest.Trim(), [System.Text.UTF8Encoding]::new($false))
    Write-Host "已生成 yizhi-web/latest.json（版本 $ver）"
}

if ($ForInstaller) {
    $pruneArgs = @{ Root = $OutputDir }
    if ($removeBundledPython) { $pruneArgs.RemoveBundledPython = $true }
    & (Join-Path $PSScriptRoot "prune_install_staging.ps1") @pruneArgs
}

Write-Host ""
Write-Host "=== 构建完成 ===" -ForegroundColor Green
Write-Host "目录: $OutputDir"
if ($ForInstaller) {
    Write-Host "测试: cd `"$OutputDir`" ; .\YizhiStart.bat"
} else {
    Write-Host "测试: cd `"$OutputDir`" ; .\启动易知.bat"
}
Write-Host "打包: 使用 7-Zip 或 Inno Setup 压缩/安装"
