#Requires -Version 5.1
<#
.SYNOPSIS
  Prepare Electron in dev tree (npm install + vendor sync) before installer build.

.EXAMPLE
  .\scripts\build-electron.ps1
#>
param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ElectronDir = Join-Path $Root "electron"

if (-not (Test-Path (Join-Path $ElectronDir "package.json"))) {
    throw "electron/package.json not found"
}

Write-Host "=== Yizhi Electron build ===" -ForegroundColor Cyan
Write-Host "Dir: $ElectronDir"

Push-Location $ElectronDir
if (-not $SkipInstall) {
    Write-Host "`nnpm install ..." -ForegroundColor Yellow
    npm install --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) {
        Pop-Location
        throw "npm install failed (exit $LASTEXITCODE)"
    }
}

Write-Host "`nSync vendor assets ..." -ForegroundColor Yellow
npm run build
if ($LASTEXITCODE -ne 0) {
    Pop-Location
    throw "npm run build failed (exit $LASTEXITCODE)"
}

$electronExe = Join-Path $ElectronDir "node_modules\electron\dist\electron.exe"
$d3Vendor = Join-Path $ElectronDir "renderer\vendor\d3\d3.min.js"
$fvVendor = Join-Path $ElectronDir "renderer\vendor\file-viewer\flyfish-file-viewer-web-full.iife.js"

foreach ($p in @($electronExe, $d3Vendor, $fvVendor)) {
    if (-not (Test-Path $p)) {
        Pop-Location
        throw "Missing build artifact: $p"
    }
}

$ver = (Get-Content (Join-Path $ElectronDir "package.json") -Raw | ConvertFrom-Json).version
Pop-Location

Write-Host ""
Write-Host "Electron ready v$ver" -ForegroundColor Green
Write-Host "  $electronExe"
Write-Host ""
Write-Host "Next: .\scripts\build-installer.ps1 -LicenseServer ... -JwtSecret ..."
