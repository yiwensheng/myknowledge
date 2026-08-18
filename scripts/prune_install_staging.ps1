#Requires -Version 5.1
<#
.SYNOPSIS
  安装包 staging 最小化：删除运行时不需要的测试、文档、源码 map 等。

.DESCRIPTION
  在 build-portable.ps1 -ForInstaller 末尾调用。只删已知安全项，不删 prompts/、lib/、backend/ 等运行必需目录。
  -RemoveBundledPython：删除构建期留下的完整 python\（安装版仅用 runtime\yizhi-backend.exe）。
#>
param(
    [Parameter(Mandatory)]
    [string]$Root,
    [switch]$RemoveBundledPython
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path $Root)) {
    throw "Staging root not found: $Root"
}

function Remove-TreeIfExists([string]$Path) {
    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Remove-GlobFiles([string]$Base, [string[]]$Patterns) {
    if (-not (Test-Path $Base)) { return }
    foreach ($pat in $Patterns) {
        Get-ChildItem -Path $Base -Recurse -Include $pat -File -ErrorAction SilentlyContinue |
            Remove-Item -Force -ErrorAction SilentlyContinue
    }
}

function Remove-NamedDirs([string]$Base, [string[]]$Names) {
    if (-not (Test-Path $Base)) { return }
    foreach ($name in $Names) {
        Get-ChildItem -Path $Base -Recurse -Directory -Filter $name -ErrorAction SilentlyContinue |
            ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
    }
}

Write-Host "=== staging 最小化（安装包）===" -ForegroundColor Cyan

# --- 顶层开发目录（复制阶段应已排除，此处兜底）---
foreach ($top in @(
    "docs", "tests", "license-server", "dist", ".git", ".ruff_cache", ".pytest_cache",
    # 勿删 skills：安装版默认工作流依赖 ROOT/skills/*/SKILL.md
    "design-md", ".cursor", ".agents", ".specify", "specs"
)) {
    Remove-TreeIfExists (Join-Path $Root $top)
}

# --- 开发用脚本：仅保留首次运行/工具链所需 ---
$scriptsDir = Join-Path $Root "scripts"
$scriptKeep = @(
    "setup_docubrowser.py",
    "setup_optional_tools.py",
    "init_wiki.py"
)
if (Test-Path $scriptsDir) {
    Get-ChildItem -Path $scriptsDir -File | ForEach-Object {
        if ($scriptKeep -notcontains $_.Name) {
            Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
        }
    }
    Remove-NamedDirs $scriptsDir @("installer", "__pycache__")
}

# --- 根目录开发 bat / 说明（安装版用 VBS 直启 Electron）---
foreach ($f in @(
    "启动易知.bat", "启动Myknowledge.bat", "STATE.md", "LOOP.md", "purpose.md",
    "env.example", ".env.example"
)) {
    $p = Join-Path $Root $f
    if (Test-Path $p) { Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue }
}

# --- Python：默认精简；A1 时可整目录删除 ---
$pyRoot = Join-Path $Root "python"
if ($RemoveBundledPython) {
    $frozen = Join-Path $Root "runtime\yizhi-backend.exe"
    if (-not (Test-Path -LiteralPath $frozen)) {
        throw "RemoveBundledPython 要求存在 runtime\yizhi-backend.exe，当前缺失: $frozen"
    }
    Write-Host "A1: 删除重复 python\（安装版仅用 runtime\yizhi-backend.exe）…" -ForegroundColor Cyan
    Remove-TreeIfExists $pyRoot
} else {
    Remove-NamedDirs $pyRoot @(
        "__pycache__", "tests", "test", "testing", "docs", "doc", "examples", "benchmarks",
        "idlelib", "turtledemo", "tkinter", "ensurepip", "venv", "pydoc_data"
    )
    Remove-GlobFiles $pyRoot @("*.pyc", "*.pyo", "*.pyi", "*.pxd", "*.c", "*.h", "*.html")
    $site = Join-Path $pyRoot "Lib\site-packages"
    Get-ChildItem -Path $site -Recurse -Directory -Filter "*.dist-info" -ErrorAction SilentlyContinue |
        ForEach-Object {
            Remove-Item -LiteralPath (Join-Path $_.FullName "RECORD") -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath (Join-Path $_.FullName "REQUESTED") -Force -ErrorAction SilentlyContinue
        }
    # 不要的可选包（若误装）
    foreach ($opt in @("pytesseract", "imageio_ffmpeg", "imageio", "playwright", "greenlet")) {
        Get-ChildItem -Path $site -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -eq $opt -or $_.Name -like "$opt-*" -or $_.Name -like "$opt.*" } |
            ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
    }
}

# --- Electron：再跑一遍 vendor 精简 + 清测试文档 ---
$electronDir = Join-Path $Root "electron"
& (Join-Path $PSScriptRoot "prune_electron_modules.ps1") -ElectronDir $electronDir
$nm = Join-Path $electronDir "node_modules"
Remove-NamedDirs $nm @(
    "test", "tests", "__tests__", "docs", "doc", "example", "examples",
    ".github", "coverage", "__mocks__", "benchmark", "benchmarks"
)
Remove-GlobFiles $nm @("*.map", "*.ts", "*.tsx", "*.mts", "*.cts", "*.flow", "CHANGELOG.md", "README.md", "readme.md")
# 重复的 file-viewer 副本（vendor 已有一份）
Remove-TreeIfExists (Join-Path $electronDir "public\file-viewer")

# --- Electron 开发脚本 ---
Remove-TreeIfExists (Join-Path $Root "electron\scripts")

# --- third_party/pdf_layout：保留 ONNX 权重（PDF 版面表格）---
$pdfLayout = Join-Path $Root "third_party\pdf_layout"
if (Test-Path $pdfLayout) {
    Write-Host "保留 pdf_layout 模型目录: $pdfLayout"
}

# --- third_party：baoyu 自带 node_modules 体积大，运行时由 bun 执行 ts；保留 lib 与 baoyu-fetch ---
$baoyuNm = Join-Path $Root "third_party\baoyu-url-to-markdown\scripts\node_modules"
Remove-TreeIfExists $baoyuNm

# --- DocuBrowser 源码中的测试/文档/截图（staging 冗余） ---
$db = Join-Path $Root "third_party\DocuBrowser"
Remove-NamedDirs $db @(
    "tests", "test", "docs", ".git", "__pycache__",
    "test_pdfs", "test_pdfs_live", "screenshots", ".claude",
    "EndUser_docs", "info_docs", "status_docs"
)
# 残留测试 PDF（目录名未命中时）
if (Test-Path $db) {
    Get-ChildItem -LiteralPath $db -Recurse -File -Filter "*.pdf" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.FullName -match '(?i)[\\/](test|sample|fixture)s?[\\/]' -or
            $_.Name -match '(?i)^(test_|sample_|fixture_)'
        } |
        ForEach-Object {
            try { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction Stop } catch {}
        }
}

# --- 在线购买页副本可留（体积小）；yizhi-web 保留 ---

Write-Host "staging 最小化完成" -ForegroundColor Green
