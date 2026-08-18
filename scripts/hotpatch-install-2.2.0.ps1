#Requires -Version 5.1
# 热修安装版 2.2.0：笔记保存 + 默认工作流 + 资料库预览
# 若非管理员会自动弹出 UAC 提升权限。
$ErrorActionPreference = "Stop"

function Test-IsAdmin {
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  $p = New-Object Security.Principal.WindowsPrincipal($id)
  return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
  Write-Host "需要管理员权限写入 C:\Program Files\Yizhi ，正在弹出 UAC…" -ForegroundColor Yellow
  $self = if ($PSCommandPath) { $PSCommandPath } else { $MyInvocation.MyCommand.Path }
  Start-Process -FilePath "powershell.exe" `
    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $self) `
    -Verb RunAs -Wait
  exit $LASTEXITCODE
}

$Root = "E:\app\Myknowledge"
$Dest = "C:\Program Files\Yizhi"
if (-not (Test-Path $Dest)) { throw "未找到安装目录: $Dest" }

# 易知若正在运行，部分文件可能被占用；能拷则拷
$pairs = @(
  @("$Root\electron\renderer\app.js", "$Dest\electron\renderer\app.js"),
  @("$Root\electron\renderer\rich-editor.js", "$Dest\electron\renderer\rich-editor.js"),
  @("$Root\electron\main.js", "$Dest\electron\main.js"),
  @("$Root\backend\server.py", "$Dest\backend\server.py"),
  @("$Root\lib\config.py", "$Dest\lib\config.py"),
  @("$Root\lib\workflows.py", "$Dest\lib\workflows.py")
)
foreach ($p in $pairs) {
  Copy-Item -LiteralPath $p[0] -Destination $p[1] -Force
  Write-Host "OK $($p[1])"
}

$rtSrc = Join-Path $Root "dist\backend-runtime"
if (Test-Path (Join-Path $rtSrc "yizhi-backend.exe")) {
  New-Item -ItemType Directory -Path "$Dest\runtime" -Force | Out-Null
  robocopy $rtSrc "$Dest\runtime" /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
  Write-Host "已更新 runtime\ (含 yizhi-backend.exe)"
} else {
  Write-Warning "缺少 dist\backend-runtime\yizhi-backend.exe。请先: .\scripts\build-backend-exe.ps1"
}

if (-not (Test-Path "$Dest\skills\wiki-ingest\SKILL.md")) {
  robocopy "$Root\skills" "$Dest\skills" /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
  Write-Host "已同步 skills\"
} else {
  Write-Host "skills\ 已存在"
}

Write-Host ""
Write-Host "热修完成。请完全退出易知后重新打开，检查：" -ForegroundColor Green
Write-Host "  - 笔记保存"
Write-Host "  - 导入资料 → 工作流"
Write-Host "  - 资料库 → 浏览（预览）"
Write-Host ""
Write-Host "按任意键关闭…"
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
