#Requires -Version 5.1
<#
.SYNOPSIS
  Patch an existing 易知 install under Program Files (admin required).
#>
param(
    [string]$InstallDir = "C:\Program Files\Yizhi",
    [string]$SourceRoot = ""
)

$ErrorActionPreference = "Stop"
if (-not $SourceRoot) {
    $SourceRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}

if (-not (Test-Path $InstallDir)) {
    throw "Install dir not found: $InstallDir"
}

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)
if (-not $isAdmin) {
    throw "Run PowerShell as Administrator to patch $InstallDir"
}

$pairs = @(
    @(
        (Join-Path $SourceRoot "scripts\installer\YizhiStart.vbs"),
        (Join-Path $InstallDir "YizhiStart.vbs")
    ),
    @(
        (Join-Path $SourceRoot "electron\main.js"),
        (Join-Path $InstallDir "electron\main.js")
    ),
    @(
        (Join-Path $SourceRoot "electron\splash.html"),
        (Join-Path $InstallDir "electron\splash.html")
    ),
    @(
        (Join-Path $SourceRoot "electron\splash.css"),
        (Join-Path $InstallDir "electron\splash.css")
    ),
    @(
        (Join-Path $SourceRoot "scripts\init_wiki.py"),
        (Join-Path $InstallDir "scripts\init_wiki.py")
    ),
    @(
        (Join-Path $SourceRoot "lib\cli.py"),
        (Join-Path $InstallDir "lib\cli.py")
    )
)

foreach ($pair in $pairs) {
    $src, $dst = $pair
    if (-not (Test-Path $src)) {
        throw "Missing source file: $src"
    }
    Copy-Item $src $dst -Force
    Write-Host "Patched: $dst"
}

$yizhiStartBat = @"
@echo off
setlocal EnableExtensions
start "" wscript.exe "%~dp0YizhiStart.vbs"
exit /b 0
"@
[System.IO.File]::WriteAllText((Join-Path $InstallDir "YizhiStart.bat"), $yizhiStartBat, [System.Text.UTF8Encoding]::new($false))
Write-Host "Patched: $(Join-Path $InstallDir 'YizhiStart.bat')"

# Redirect Start Menu / Desktop shortcuts that still point at .bat
$shell = New-Object -ComObject WScript.Shell
$linkTargets = @(
    (Join-Path $env:USERPROFILE "Desktop\易知.lnk"),
    (Join-Path $env:PUBLIC "Desktop\易知.lnk"),
    (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\易知\易知.lnk")
)
foreach ($lnkPath in $linkTargets) {
    if (-not (Test-Path -LiteralPath $lnkPath)) { continue }
    try {
        $sc = $shell.CreateShortcut($lnkPath)
        $sc.TargetPath = Join-Path $InstallDir "YizhiStart.vbs"
        $sc.WorkingDirectory = $InstallDir
        $sc.IconLocation = (Join-Path $InstallDir "electron\assets\icon.ico")
        $sc.Save()
        Write-Host "Patched shortcut: $lnkPath"
    } catch {
        Write-Warning "Shortcut patch failed: $lnkPath — $($_.Exception.Message)"
    }
}

Write-Host ""
Write-Host "Done. Double-click desktop shortcut or run:" -ForegroundColor Green
Write-Host "  wscript.exe `"$InstallDir\YizhiStart.vbs`""
