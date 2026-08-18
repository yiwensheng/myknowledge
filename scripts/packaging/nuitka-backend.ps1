#Requires -Version 5.1
<#
.SYNOPSIS
  Phase B: build yizhi-backend.exe with Nuitka into the same runtime/ layout as PyInstaller.

.DESCRIPTION
  Optional A/B — default release path remains PyInstaller (build-backend-exe.ps1).
  Requires: pip install nuitka ordered-set zstandard, and MSVC Build Tools.
#>
param(
    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) {
    $OutDir = Join-Path $Root "dist\backend-runtime"
}
$nuitkaOut = Join-Path $Root "dist\nuitka-out"

Write-Host "=== Nuitka backend (Phase B) ===" -ForegroundColor Cyan
& python -m pip install -q "nuitka" "ordered-set" "zstandard"
if ($LASTEXITCODE -ne 0) { throw "pip install nuitka failed" }

New-Item -ItemType Directory -Path $nuitkaOut -Force | Out-Null
Push-Location $Root
try {
    & python -m nuitka `
        --standalone `
        --windows-console-mode=disable `
        --output-dir="$nuitkaOut" `
        --output-filename=yizhi-backend.exe `
        --include-package=backend `
        --include-package=lib `
        --include-package=uvicorn `
        --include-package=fastapi `
        --assume-yes-for-downloads `
        "$Root\backend\__frozen_main__.py"
    if ($LASTEXITCODE -ne 0) { throw "Nuitka failed: $LASTEXITCODE" }
} finally {
    Pop-Location
}

# Nuitka standalone folder is usually __frozen_main__.dist
$distDir = Get-ChildItem $nuitkaOut -Directory -Filter "*.dist" | Select-Object -First 1
if (-not $distDir) { throw "Nuitka .dist folder not found under $nuitkaOut" }
$builtExe = Join-Path $distDir.FullName "yizhi-backend.exe"
if (-not (Test-Path $builtExe)) { throw "Missing $builtExe" }

if (Test-Path $OutDir) { Remove-Item $OutDir -Recurse -Force }
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
Copy-Item (Join-Path $distDir.FullName "*") $OutDir -Recurse -Force
Write-Host "OK: $(Join-Path $OutDir 'yizhi-backend.exe')" -ForegroundColor Green
