#Requires -Version 5.1
<#
.SYNOPSIS
  Prepare third_party/pdf_layout/detection.onnx for Yizhi PDF layout.

.NOTES
  Preferred (works via hf-mirror when direct ONNX repo is missing):
    $env:HF_ENDPOINT='https://hf-mirror.com'
    python scripts/export_tatr_detection_onnx.py

  Fallback: try download preconverted ONNX URLs (often 404 / blocked).
#>
param(
    [string]$OutDir = "",
    [switch]$SkipExport
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) {
    $OutDir = Join-Path $Root "third_party\pdf_layout"
}
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
$dest = Join-Path $OutDir "detection.onnx"
if ((Test-Path $dest) -and (Get-Item $dest).Length -gt 1MB) {
    Write-Host "Already present: $dest"
    exit 0
}

if (-not $SkipExport) {
    Write-Host "Exporting microsoft/table-transformer-detection via HF mirror ..."
    $env:HF_ENDPOINT = "https://hf-mirror.com"
    & python (Join-Path $PSScriptRoot "export_tatr_detection_onnx.py")
    if ((Test-Path $dest) -and (Get-Item $dest).Length -gt 1MB) {
        Write-Host "OK: $dest"
        exit 0
    }
    Write-Warning "Export failed; trying direct download URLs ..."
}

$urls = @(
    "https://hf-mirror.com/onnx-community/table-transformer-detection-ONNX/resolve/main/onnx/model.onnx",
    "https://huggingface.co/onnx-community/table-transformer-detection-ONNX/resolve/main/onnx/model.onnx"
)

$ok = $false
foreach ($url in $urls) {
    Write-Host "Downloading: $url"
    try {
        $tmp = Join-Path $OutDir "detection.onnx.part"
        if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
            & curl.exe -fL --retry 2 --retry-delay 2 --connect-timeout 20 --max-time 180 -o $tmp $url
            if ($LASTEXITCODE -ne 0) { throw "curl exit $LASTEXITCODE" }
        } else {
            Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
        }
        if ((Test-Path $tmp) -and (Get-Item $tmp).Length -gt 1MB) {
            Move-Item $tmp $dest -Force
            $ok = $true
            $mb = [math]::Round((Get-Item $dest).Length / 1MB, 1)
            Write-Host "Saved: $dest ($mb MB)"
            break
        }
    } catch {
        Write-Warning "$_"
        Remove-Item (Join-Path $OutDir "detection.onnx.part") -ErrorAction SilentlyContinue
    }
}

if (-not $ok) {
    Write-Warning "Failed. Place detection.onnx manually at: $dest"
    Write-Warning "Or run: python scripts/export_tatr_detection_onnx.py  (needs torch/transformers/timm/onnx)"
    exit 0
}
