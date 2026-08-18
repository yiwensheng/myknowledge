#Requires -Version 5.1
<#
.SYNOPSIS
  商业化发布前自检：本地交付物 + 可选远程授权服务

.EXAMPLE
  .\scripts\run_commercial_preflight.ps1
  .\scripts\run_commercial_preflight.ps1 -LicenseServer https://www.yzwhysxx.cn/license -AdminKey xxx -JwtSecret xxx
#>
param(
    [string]$LicenseServer = "https://www.yzwhysxx.cn/license",
    [string]$AdminKey = "",
    [string]$JwtSecret = "",
    [switch]$SkipRemote
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Push-Location $Root

Write-Host "=== 1/3 本地交付物 ===" -ForegroundColor Cyan
python scripts/verify_commercial_phases.py
if ($LASTEXITCODE -ne 0) { Pop-Location; exit 1 }

if ($SkipRemote) {
    Write-Host "`n已跳过远程检查 (-SkipRemote)" -ForegroundColor Yellow
    Pop-Location
    exit 0
}

Write-Host "`n=== 2/3 远程 health / plans ===" -ForegroundColor Cyan
try {
    $health = Invoke-RestMethod -Uri "$LicenseServer/health" -TimeoutSec 20
    $plans = Invoke-RestMethod -Uri "$LicenseServer/license/plans" -TimeoutSec 20
    Write-Host "health: $($health | ConvertTo-Json -Compress)"
    Write-Host "plans:  $($plans | ConvertTo-Json -Compress)"
} catch {
    Write-Host "远程检查失败: $_" -ForegroundColor Red
    Pop-Location
    exit 1
}

if ($AdminKey -and $JwtSecret) {
    Write-Host "`n=== 3/3 test_license_flow ===" -ForegroundColor Cyan
    $env:TEST_LICENSE_SERVER = $LicenseServer
    $env:LICENSE_ADMIN_KEY = $AdminKey
    $env:LICENSE_JWT_SECRET = $JwtSecret
    python scripts/test_license_flow.py
    if ($LASTEXITCODE -ne 0) { Pop-Location; exit 1 }
} else {
    Write-Host "`n=== 3/3 跳过 test_license_flow（未提供 -AdminKey / -JwtSecret）===" -ForegroundColor Yellow
}

Write-Host "`n=== preflight 通过 ===" -ForegroundColor Green
Pop-Location
