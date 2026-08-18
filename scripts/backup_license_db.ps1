#Requires -Version 5.1
<#
.SYNOPSIS
  备份 license-server 的 license.db（Windows 服务器计划任务用）

.EXAMPLE
  .\scripts\backup_license_db.ps1
  .\scripts\backup_license_db.ps1 -DbPath C:\yizhi\license-server\license.db -KeepDays 30
#>
param(
    [string]$DbPath = "C:\yizhi\license-server\license.db",
    [string]$BackupDir = "C:\yizhi\license-server\backups",
    [int]$KeepDays = 30
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path $DbPath)) {
    Write-Error "找不到数据库: $DbPath"
}
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dest = Join-Path $BackupDir "license-$stamp.db"
Copy-Item -Path $DbPath -Destination $dest -Force
Write-Host "已备份: $dest"

if ($KeepDays -gt 0) {
    $cutoff = (Get-Date).AddDays(-$KeepDays)
    Get-ChildItem $BackupDir -Filter "license-*.db" |
        Where-Object { $_.LastWriteTime -lt $cutoff } |
        ForEach-Object {
            Remove-Item $_.FullName -Force
            Write-Host "已删除旧备份: $($_.Name)"
        }
}
