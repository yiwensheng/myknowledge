#Requires -Version 5.1
<#
.SYNOPSIS
  安装 Inno Setup 6（用于 build-installer.ps1 编译 .exe 安装包）

.DESCRIPTION
  本机无 winget 或 ISCC 未在 PATH 时，从 GitHub 官方 Release 下载并静默安装。
  安装后 ISCC 位于：C:\Program Files (x86)\Inno Setup 6\ISCC.exe

.EXAMPLE
  .\scripts\install-innosetup.ps1
  .\scripts\install-innosetup.ps1 -InstallerPath D:\Downloads\innosetup-6.7.3.exe
#>
param(
    [string]$InstallerPath = ""
)

$ErrorActionPreference = "Stop"
$IsccPath = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (Test-Path $IsccPath) {
    Write-Host "Inno Setup 6 已安装: $IsccPath" -ForegroundColor Green
    exit 0
}

if (-not $InstallerPath) {
    $InstallerPath = Join-Path $env:TEMP "innosetup-6.7.3.exe"
}

if (-not (Test-Path $InstallerPath)) {
    $url = "https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe"
    Write-Host "下载 Inno Setup 6.7.3 ..."
    Write-Host "  $url"
    $downloaded = $false
    try {
        Invoke-WebRequest -Uri $url -OutFile $InstallerPath -UseBasicParsing
        $downloaded = $true
    } catch {
        Write-Warning "Invoke-WebRequest 失败: $_"
    }
    if (-not $downloaded -and (Get-Command curl.exe -ErrorAction SilentlyContinue)) {
        Write-Host "改用 curl 重试（--ssl-no-revoke）..."
        & curl.exe --ssl-no-revoke -L -o $InstallerPath $url
        if ($LASTEXITCODE -eq 0 -and (Test-Path $InstallerPath)) {
            $downloaded = $true
        }
    }
    if (-not $downloaded) {
        Write-Host ""
        Write-Host "自动下载失败。请手动操作：" -ForegroundColor Yellow
        Write-Host "  1. 浏览器打开: https://jrsoftware.org/isdl.php"
        Write-Host "  2. 下载 innosetup-6.7.3.exe（GitHub 链接）"
        Write-Host "  3. 运行: .\scripts\install-innosetup.ps1 -InstallerPath `"下载路径\innosetup-6.7.3.exe`""
        exit 2
    }
}

$size = (Get-Item $InstallerPath).Length
if ($size -lt 1000000) {
    throw "安装包文件过小 ($size 字节)，可能下载不完整: $InstallerPath"
}

Write-Host "安装 Inno Setup（静默）..."
$proc = Start-Process -FilePath $InstallerPath -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART","/SP-" -Wait -PassThru
if ($proc.ExitCode -ne 0) {
    throw "Inno Setup 安装失败，退出码: $($proc.ExitCode)"
}

if (-not (Test-Path $IsccPath)) {
    throw "安装完成但未找到 ISCC: $IsccPath"
}

Write-Host "安装成功: $IsccPath" -ForegroundColor Green
