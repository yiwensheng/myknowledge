#Requires -Version 5.1
<#
.SYNOPSIS
  构建易知 Windows 安装包（Inno Setup）

.DESCRIPTION
  1. 调用 build-portable.ps1 -ForInstaller（默认编 runtime\ 并删除重复 python\；可用 -KeepBundledPythonFallback）
  2. 使用 Inno Setup 6 编译 Yizhi-Setup-x.x.x.exe
  3. 安装向导可选：桌面快捷方式、开机自启（当前用户 HKCU Run）

  用户机器无需预装 Python / Node.js。构建时会下载并打入 VC++ Redist；
  安装时若系统缺失则自动静默安装（/install /quiet /norestart）。
  正式安装包运行时只依赖 runtime\yizhi-backend.exe + Electron（方案 A1）。

.PARAMETER LicenseServer
  注入 .env.user 的 MYKNOWLEDGE_LICENSE_SERVER

.PARAMETER JwtSecret
  注入 MYKNOWLEDGE_LICENSE_JWT_SECRET

.PARAMETER EnvFile
  大模型配置源 .env，默认项目根 .env

.PARAMETER InnoSetupPath
  ISCC.exe 路径；默认自动探测

.PARAMETER SkipPortableBuild
  跳过 staging 重建（仅重新编译 iss，调试用）

.PARAMETER SkipTools
  传给 build-portable：跳过 ffmpeg/bun

.PARAMETER SkipDocubrowser
  传给 build-portable：跳过 DocuBrowser 安装

.PARAMETER SkipVCRedistDownload
  不下载 VC++ Redist（须已放入 staging/redist/）

.PARAMETER InstallInnoSetup
  未找到 ISCC 时尝试自动安装 Inno Setup 6

.EXAMPLE
  .\scripts\build-installer.ps1 `
    -LicenseServer "https://www.yzwhysxx.cn/license" `
    -JwtSecret "<LICENSE_JWT_SECRET>"

  需先安装 Inno Setup 6：
  winget install --id JRSoftware.InnoSetup -e
#>
param(
    [string]$LicenseServer = "",
    [string]$JwtSecret = "",
    [string]$EnvFile = "",
    [string]$InnoSetupPath = "",
    [string]$StagingDir = "",
    [string]$OutputDir = "",
    [switch]$SkipPortableBuild,
    [switch]$SkipTools,
    [switch]$SkipDocubrowser,
    [switch]$SkipVCRedistDownload,
    [switch]$InstallInnoSetup,
    [switch]$SkipBackendBinary,
    [switch]$KeepBundledPythonFallback
)

$VCRedistUrl = "https://aka.ms/vs/17/release/vc_redist.x64.exe"

function Ensure-VCRedist {
    param([string]$Dir, [switch]$SkipDownload)
    $redistDir = Join-Path $Dir "redist"
    $redistExe = Join-Path $redistDir "vc_redist.x64.exe"
    if (Test-Path $redistExe) {
        $sizeMb = [math]::Round((Get-Item $redistExe).Length / 1MB, 1)
        Write-Host "VC++ Redist 已就绪: $redistExe ($sizeMb MB)"
        return $redistExe
    }
    if ($SkipDownload) {
        throw "缺少 VC++ Redist: $redistExe`n请下载 $VCRedistUrl 放到该路径，或去掉 -SkipVCRedistDownload"
    }
    New-Item -ItemType Directory -Path $redistDir -Force | Out-Null
    Write-Host "下载 VC++ Redistributable x64 ..."
    Write-Host "  $VCRedistUrl"
    $downloaded = $false
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl) {
        & curl.exe -fsSL --retry 5 --retry-delay 2 -o $redistExe $VCRedistUrl
        if ($LASTEXITCODE -eq 0 -and (Test-Path $redistExe) -and (Get-Item $redistExe).Length -gt 1MB) {
            $downloaded = $true
        }
    }
    if (-not $downloaded) {
        Invoke-WebRequest -Uri $VCRedistUrl -OutFile $redistExe -UseBasicParsing
    }
    if (-not (Test-Path $redistExe) -or (Get-Item $redistExe).Length -lt 1MB) {
        throw "VC++ Redist 下载失败"
    }
    Write-Host "已保存: $redistExe"
    return $redistExe
}

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$IssFile = Join-Path $PSScriptRoot "installer\YizhiSetup.iss"

$ver = (Get-Content (Join-Path $Root "electron\package.json") -Raw | ConvertFrom-Json).version
if (-not $StagingDir) {
    # 每次用带时间戳的新目录，避免旧 staging 被 Electron/资源管理器锁死导致构建失败
    $stamp = Get-Date -Format "yyyyMMddHHmmss"
    $StagingDir = Join-Path $Root "dist\Yizhi-Staging-$ver-$stamp"
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $Root "dist"
}

function Find-ISCC {
    param([string]$Explicit)
    if ($Explicit -and (Test-Path $Explicit)) { return $Explicit }
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

Write-Host "=== 易知安装包构建 ===" -ForegroundColor Cyan
Write-Host "版本:   $ver"
Write-Host "Staging: $StagingDir"
Write-Host "输出:   $OutputDir"

$iconScript = Join-Path $PSScriptRoot "installer\build-app-icon.ps1"
$installerIco = Join-Path $PSScriptRoot "installer\Yizhi.ico"
$appIco = Join-Path $Root "electron\assets\icon.ico"
Write-Host "`n--- 生成易知图标（多尺寸 .ico）---" -ForegroundColor Cyan
& $iconScript -OutputIco $installerIco
Copy-Item $installerIco $appIco -Force

if (-not $SkipPortableBuild) {
    $portableArgs = @{
        OutputDir         = $StagingDir
        ForInstaller      = $true
    }
    if ($LicenseServer) { $portableArgs.LicenseServer = $LicenseServer }
    if ($JwtSecret) { $portableArgs.JwtSecret = $JwtSecret }
    if ($EnvFile) { $portableArgs.EnvFile = $EnvFile }
    if ($SkipTools) { $portableArgs.SkipTools = $true }
    if ($SkipDocubrowser) { $portableArgs.SkipDocubrowser = $true }
    if ($SkipBackendBinary) { $portableArgs.SkipBackendBinary = $true }
    if ($KeepBundledPythonFallback) { $portableArgs.KeepBundledPythonFallback = $true }

    Write-Host "`n--- 1/2 生成安装 staging（runtime 后端 + Electron；默认无重复 python\）---" -ForegroundColor Cyan
    # 释放可能锁住旧固定路径 staging 的 Electron（新默认已用时间戳目录，此项为安全网）
    $legacyStage = Join-Path $Root "dist\Yizhi-Staging-$ver"
    foreach ($candidate in @($StagingDir, $legacyStage) | Select-Object -Unique) {
        if (-not $candidate) { continue }
        $stageNorm = $candidate.TrimEnd('\')
        try {
            Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | ForEach-Object {
                if ($_.ProcessId -eq $PID) { return }
                $ep = $_.ExecutablePath
                $cl = $_.CommandLine
                $name = $_.Name
                $isApp = $name -match '^(electron|python|pythonw)\.exe$'
                $hit = $false
                if ($ep -and $ep.StartsWith($stageNorm, [StringComparison]::OrdinalIgnoreCase)) { $hit = $true }
                elseif ($isApp -and $cl -and $cl.IndexOf($stageNorm, [StringComparison]::OrdinalIgnoreCase) -ge 0) { $hit = $true }
                if ($hit) {
                    Write-Host "  结束占用进程 PID=$($_.ProcessId) $name"
                    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
                }
            }
        } catch {
            # ignore process scan errors
        }
    }
    Start-Sleep -Milliseconds 400

    & (Join-Path $Root "scripts\build-portable.ps1") @portableArgs
    if ($LASTEXITCODE -ne 0) { throw "build-portable 失败" }
    $marker = Join-Path $Root "dist\.yizhi-last-output.txt"
    if (Test-Path -LiteralPath $marker) {
        $resolved = (Get-Content -LiteralPath $marker -Raw).Trim()
        if ($resolved -and (Test-Path -LiteralPath $resolved)) {
            if ($resolved -ne $StagingDir) {
                Write-Host "Staging 实际路径: $resolved" -ForegroundColor Yellow
            }
            $StagingDir = $resolved
        }
    }
} else {
    Write-Host "`n--- 跳过 staging（-SkipPortableBuild）---" -ForegroundColor Yellow
    if (-not (Test-Path $StagingDir)) {
        throw "Staging 不存在: $StagingDir"
    }
    $stagingIco = Join-Path $StagingDir "electron\assets\icon.ico"
    if (-not (Test-Path (Split-Path $stagingIco -Parent))) {
        New-Item -ItemType Directory -Path (Split-Path $stagingIco -Parent) -Force | Out-Null
    }
    Copy-Item $appIco $stagingIco -Force
}

Ensure-VCRedist -Dir $StagingDir -SkipDownload:$SkipVCRedistDownload | Out-Null

$required = @(
    (Join-Path $StagingDir "electron\node_modules\electron\dist\electron.exe"),
    (Join-Path $StagingDir "electron\assets\icon.ico"),
    (Join-Path $StagingDir "YizhiStart.vbs"),
    (Join-Path $StagingDir "YizhiStart.bat"),
    (Join-Path $StagingDir "redist\vc_redist.x64.exe"),
    $installerIco,
    (Join-Path $PSScriptRoot "installer\languages\ChineseSimplified.isl"),
    (Join-Path $PSScriptRoot "installer\installer-highlights.txt")
)
if ($SkipBackendBinary) {
    $required = @(Join-Path $StagingDir "python\python.exe") + $required
} else {
    $required = @(Join-Path $StagingDir "runtime\yizhi-backend.exe") + $required
    # A1：默认无 python\；仅诊断包 -KeepBundledPythonFallback 保留
    $pyFallback = Join-Path $StagingDir "python\python.exe"
    if (Test-Path $pyFallback) {
        if ($KeepBundledPythonFallback) {
            Write-Host "诊断模式：保留 python\ 回退 ($pyFallback)"
        } else {
            Write-Warning "staging 仍含 python\；期望 A1 已删除。若刚改脚本请确认 prune_install_staging -RemoveBundledPython。"
        }
    } else {
        Write-Host "A1 OK: staging 无重复 python\（仅 runtime\yizhi-backend.exe）"
    }
}
foreach ($p in $required) {
    if (-not (Test-Path $p)) {
        # 兼容旧 staging（venv 布局）；正式包应使用 python\python.exe
        if ($p -like "*python\python.exe") {
            $legacy = Join-Path $StagingDir "python\Scripts\python.exe"
            if (Test-Path $legacy) {
                Write-Warning "检测到旧版 venv 布局 ($legacy)。该包在其它电脑会失败，请重新 build-portable。"
                continue
            }
        }
        throw "Staging 不完整，缺少: $p"
    }
}

# 拒绝把绑定开发机路径的 venv 打进安装包（仅当仍含 python\ 时检查）
$venvCfg = Join-Path $StagingDir "python\pyvenv.cfg"
if (Test-Path $venvCfg) {
    throw "Staging 的 python\pyvenv.cfg 表明仍为 venv（不可搬迁）。请重新运行 build-portable.ps1 后再打安装包。"
}

$iscc = Find-ISCC -Explicit $InnoSetupPath
if (-not $iscc -and $InstallInnoSetup) {
    Write-Host "未找到 ISCC，尝试安装 Inno Setup 6 ..." -ForegroundColor Yellow
    & (Join-Path $Root "scripts\install-innosetup.ps1")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $iscc = Find-ISCC -Explicit $InnoSetupPath
}
if (-not $iscc) {
    Write-Host ""
    Write-Host "未找到 Inno Setup 6 (ISCC.exe)。" -ForegroundColor Red
    Write-Host ""
    Write-Host "方式 A（推荐）：手动下载后安装"
    Write-Host "  1. 打开 https://jrsoftware.org/isdl.php"
    Write-Host "  2. 下载 innosetup-6.7.3.exe"
    Write-Host "  3. 运行: .\scripts\install-innosetup.ps1 -InstallerPath `"下载路径\innosetup-6.7.3.exe`""
    Write-Host ""
    Write-Host "方式 B：自动安装（需能访问 GitHub）"
    Write-Host "  .\scripts\build-installer.ps1 ... -InstallInnoSetup"
    Write-Host ""
    Write-Host "方式 C：已有 ISCC 时指定路径"
    Write-Host "  .\scripts\build-installer.ps1 ... -InnoSetupPath `"C:\Program Files (x86)\Inno Setup 6\ISCC.exe`""
    Write-Host ""
    Write-Host "Staging 已就绪，可手动编译（PowerShell 须加 & 调用）："
    Write-Host "  & `"C:\Program Files (x86)\Inno Setup 6\ISCC.exe`" /DMyAppVersion=$ver /DMyAppVersionFour=$ver.0 /DSourceDir=`"$StagingDir`" /DOutputDir=`"$OutputDir`" `"$IssFile`""
    exit 2
}

Write-Host "`n--- 2/2 Inno Setup 编译 ---" -ForegroundColor Cyan
Write-Host "ISCC: $iscc"

$verFour = $ver
if ($ver -match '^\d+\.\d+\.\d+$') {
    $verFour = "$ver.0"
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$stagingForIss = $StagingDir -replace '\\', '\\'
$outputForIss = $OutputDir -replace '\\', '\\'

& $iscc `
    "/DMyAppVersion=$ver" `
    "/DMyAppVersionFour=$verFour" `
    "/DSourceDir=$StagingDir" `
    "/DOutputDir=$OutputDir" `
    $IssFile

if ($LASTEXITCODE -ne 0) { throw "ISCC 编译失败 (exit $LASTEXITCODE)" }

$setupExe = Join-Path $OutputDir "Yizhi-Setup-$ver.exe"
Write-Host ""
Write-Host "=== 安装包构建完成 ===" -ForegroundColor Green
if (Test-Path $setupExe) {
    $sizeMb = [math]::Round((Get-Item $setupExe).Length / 1MB, 1)
    Write-Host ("文件: {0} ({1} MB)" -f $setupExe, $sizeMb)
} else {
    Write-Host "请检查输出目录: $OutputDir"
}
Write-Host ""
Write-Host "验收建议:"
Write-Host "  1. 干净 VM（无 Python/Node）静默安装: Yizhi-Setup-$ver.exe /VERYSILENT /SUPPRESSMSGBOXES"
Write-Host "  2. 图形安装勾选「开机自动启动」后重启，确认易知自启"
Write-Host "  3. 卸载后确认开始菜单项与 HKCU Run\Yizhi 已清除"
Write-Host "  4. 将 dist\Yizhi-Setup-$ver.exe 手动压成 Yizhi-Setup-$ver.zip，连同 latest.json、changelog.html 上传到服务器 yizhi/（对外链接须为 .zip）"
Write-Host "     验证: curl https://www.yzwhysxx.cn/yizhi/latest.json"
