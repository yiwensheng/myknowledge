#Requires -Version 5.1
<#
.SYNOPSIS
  Build yizhi-backend.exe (PyInstaller onedir) into a runtime/ folder.

.PARAMETER OutDir
  Destination directory (will contain yizhi-backend.exe + _internal/). Default: dist/backend-runtime

.PARAMETER Clean
  Remove previous work/output before build.
#>
param(
    [string]$OutDir = "",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) {
    $OutDir = Join-Path $Root "dist\backend-runtime"
}
$work = Join-Path $Root "dist\pyinstaller-work"
$spec = Join-Path $PSScriptRoot "packaging\yizhi-backend.spec"
$built = Join-Path $Root "dist\yizhi-backend"

Write-Host "=== 构建 yizhi-backend.exe (PyInstaller onedir) ===" -ForegroundColor Cyan
Write-Host "OutDir: $OutDir"

if ($Clean) {
    Remove-Item $work, $built, $OutDir -Recurse -Force -ErrorAction SilentlyContinue
}

# Ensure PyInstaller is available
$pi = & python -c "import PyInstaller; print(PyInstaller.__version__)" 2>$null
if (-not $pi) {
    Write-Host "Installing pyinstaller..."
    & python -m pip install "pyinstaller>=6.3" -q
    if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller failed" }
}

New-Item -ItemType Directory -Path (Split-Path $OutDir -Parent) -Force | Out-Null
# Isolate from pollution like D:\LazyLLM on PYTHONPATH (pulls torch/scipy into the freeze)
$prevPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = $Root
Push-Location $Root
try {
    & python -m PyInstaller --noconfirm --distpath (Join-Path $Root "dist") --workpath $work $spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed: exit $LASTEXITCODE" }
} finally {
    Pop-Location
    if ($null -eq $prevPythonPath) { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue }
    else { $env:PYTHONPATH = $prevPythonPath }
}

$exe = Join-Path $built "yizhi-backend.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "Missing $exe"
}

if (Test-Path -LiteralPath $OutDir) {
    Remove-Item -LiteralPath $OutDir -Recurse -Force
}
Copy-Item -LiteralPath $built -Destination $OutDir -Recurse
Write-Host "OK: $(Join-Path $OutDir 'yizhi-backend.exe')" -ForegroundColor Green
exit 0
