#Requires -Version 5.1
<#
.SYNOPSIS
  在 Windows 服务器注册 license.db 每日备份计划任务

.EXAMPLE
  .\scripts\setup_license_backup_task.ps1 -DbPath C:\yizhi\license-server\license.db
#>
param(
    [string]$DbPath = "C:\yizhi\license-server\license.db",
    [string]$BackupDir = "C:\yizhi\license-server\backups",
    [string]$TaskName = "YizhiLicenseDbBackup",
    [string]$RunAt = "03:00"
)

$ErrorActionPreference = "Stop"
$ScriptPath = Join-Path $PSScriptRoot "backup_license_db.ps1"
if (-not (Test-Path $ScriptPath)) {
    Write-Error "找不到 $ScriptPath"
}

$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`" -DbPath `"$DbPath`" -BackupDir `"$BackupDir`""
$Trigger = New-ScheduledTaskTrigger -Daily -At $RunAt
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings `
    -Description "易知 license.db 每日备份" -Force | Out-Null

Write-Host "已注册计划任务: $TaskName （每天 $RunAt）"
Write-Host "备份目录: $BackupDir"
