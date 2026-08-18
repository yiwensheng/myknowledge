# Yizhi promo screen-record launcher
# Usage:
#   powershell -File e:\app\Myknowledge\scripts\promo-record\record-promo.ps1
# Optional:
#   -Theme light|dark -OutDir E:\videos -DwellMs 1200 -SkipAudio

param(
  [ValidateSet("light", "dark")]
  [string]$Theme = "light",
  [string]$OutDir = "",
  [int]$DwellMs = 900,
  [switch]$SkipAudio
)

$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Electron = Join-Path (Resolve-Path (Join-Path $Here "..\..")).Path "electron"

if (-not (Test-Path (Join-Path $Electron "node_modules\electron"))) {
  Write-Host "[promo] npm install in electron/"
  Push-Location $Electron
  npm install
  Pop-Location
}

if (-not (Test-Path (Join-Path $Here "node_modules\playwright"))) {
  Write-Host "[promo] npm install in promo-record/"
  Push-Location $Here
  npm install
  Pop-Location
}

$env:PROMO_THEME = $Theme
$env:PROMO_DWELL_MS = "$DwellMs"
if ($OutDir) { $env:PROMO_OUT = $OutDir }
if ($SkipAudio) { $env:PROMO_SKIP_AUDIO = "1" }

Write-Host "[promo] Recording starts. Close any running Yizhi first; do not touch mouse/keyboard."
Push-Location $Here
try {
  node record-demo.cjs
} finally {
  Pop-Location
}
