#Requires -Version 5.1
<#
.SYNOPSIS
  从 electron/assets/icon-256.png 生成 Windows 多尺寸 .ico（安装包与快捷方式用）

.NOTES
  Inno Setup 不接受 PNG 压缩的 ICO；优先用 ImageMagick 生成传统 BMP 格式。
#>
param(
    [string]$SourcePng = "",
    [string]$OutputIco = "",
    [int[]]$Sizes = @(16, 24, 32, 48, 64, 128, 256)
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $SourcePng) { $SourcePng = Join-Path $Root "electron\assets\icon-256.png" }
if (-not $OutputIco) { $OutputIco = Join-Path $PSScriptRoot "Yizhi.ico" }

if (-not (Test-Path $SourcePng)) {
    throw "缺少图标源文件: $SourcePng"
}

function Save-PngAsIcoWithMagick {
    param(
        [Parameter(Mandatory)][string]$InputPng,
        [Parameter(Mandatory)][string]$OutIco,
        [int[]]$IconSizes
    )
    $magick = Get-Command magick -ErrorAction SilentlyContinue
    if (-not $magick) {
        return $false
    }
    $sizeArg = ($IconSizes | Sort-Object -Descending) -join ","
    # -compress None: avoid PNG-compressed 256px frames; Explorer list view needs BMP-style ICO
    & $magick.Source $InputPng -background none -alpha on `
        -define "icon:auto-resize=$sizeArg" `
        -compress None `
        $OutIco
    if ($LASTEXITCODE -ne 0) {
        throw "ImageMagick 生成 .ico 失败 (exit $LASTEXITCODE)"
    }
    return $true
}

function Save-PngAsIcoWithDrawing {
    param(
        [Parameter(Mandatory)][string]$InputPng,
        [Parameter(Mandatory)][string]$OutIco,
        [int[]]$IconSizes
    )
    Add-Type -AssemblyName System.Drawing
    $source = [System.Drawing.Bitmap]::FromFile((Resolve-Path $InputPng))
    try {
        $ms = New-Object System.IO.MemoryStream
        $bw = New-Object System.IO.BinaryWriter($ms)
        $bw.Write([UInt16]0)
        $bw.Write([UInt16]1)
        $bw.Write([UInt16]$IconSizes.Count)

        $pngList = New-Object System.Collections.Generic.List[byte[]]
        foreach ($size in $IconSizes) {
            $bmp = New-Object System.Drawing.Bitmap $size, $size
            try {
                $g = [System.Drawing.Graphics]::FromImage($bmp)
                try {
                    $g.Clear([System.Drawing.Color]::Transparent)
                    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
                    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
                    $g.DrawImage($source, 0, 0, $size, $size)
                } finally { $g.Dispose() }
                $pngMs = New-Object System.IO.MemoryStream
                try { $bmp.Save($pngMs, [System.Drawing.Imaging.ImageFormat]::Png) }
                finally { $pngMs.Dispose() }
                $pngList.Add($pngMs.ToArray())
            } finally { $bmp.Dispose() }
        }

        $offset = 6 + (16 * $IconSizes.Count)
        foreach ($size in $IconSizes) {
            $w = if ($size -ge 256) { [byte]0 } else { [byte]$size }
            $h = if ($size -ge 256) { [byte]0 } else { [byte]$size }
            $bw.Write($w)
            $bw.Write($h)
            $bw.Write([byte]0)
            $bw.Write([byte]0)
            $bw.Write([UInt16]1)
            $bw.Write([UInt16]32)
        }
        $idx = 0
        foreach ($size in $IconSizes) {
            $pngBytes = $pngList[$idx++]
            $bw.Write([UInt32]$pngBytes.Length)
            $bw.Write([UInt32]$offset)
            $offset += $pngBytes.Length
        }
        foreach ($pngBytes in $pngList) { $bw.Write($pngBytes) }
        $bw.Flush()
        [IO.File]::WriteAllBytes($OutIco, $ms.ToArray())
    } finally {
        $source.Dispose()
    }
}

$usedMagick = Save-PngAsIcoWithMagick -InputPng $SourcePng -OutIco $OutputIco -IconSizes $Sizes
if (-not $usedMagick) {
    Write-Host "未找到 ImageMagick，回退 System.Drawing（Inno Setup 可能报 Icon invalid；建议安装 ImageMagick）" -ForegroundColor Yellow
    Save-PngAsIcoWithDrawing -InputPng $SourcePng -OutIco $OutputIco -IconSizes $Sizes
}

$kb = [math]::Round((Get-Item $OutputIco).Length / 1KB, 1)
Write-Host "已生成: $OutputIco ($kb KB, sizes: $($Sizes -join ','))"
