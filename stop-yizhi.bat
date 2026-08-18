@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1

set "MYK_ROOT=%~dp0"
if "%MYK_ROOT:~-1%"=="\" set "MYK_ROOT=%MYK_ROOT:~0,-1%"

set "MYK_PORT=18765"
set "DB_PORT=18766"
if exist "%MYK_ROOT%\.env" (
  for /f "usebackq eol=# delims=" %%L in (`findstr /B /I /R "^MYKNOWLEDGE_PORT=" "%MYK_ROOT%\.env" 2^>nul`) do (
    for /f "tokens=2 delims==" %%P in ("%%L") do (
      if not "%%P"=="" set "MYK_PORT=%%P"
    )
  )
  for /f "usebackq eol=# delims=" %%L in (`findstr /B /I /R "^MYKNOWLEDGE_DOCUBROWSER_PORT=" "%MYK_ROOT%\.env" 2^>nul`) do (
    for /f "tokens=2 delims==" %%P in ("%%L") do (
      if not "%%P"=="" set "DB_PORT=%%P"
    )
  )
)

echo [易知] 正在停止旧实例并释放端口 %MYK_PORT% / %DB_PORT% ...

set "MYK_ROOT=%MYK_ROOT:\=\\%"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root='%MYK_ROOT%'; $port=[int]'%MYK_PORT%'; $dbPort=[int]'%DB_PORT%';" ^
  "$rootLike=$root -replace '\\\\','\\';" ^
  "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {" ^
  "  $_.CommandLine -and (" ^
  "    ($_.Name -eq 'electron.exe' -and $_.CommandLine -like \"*$rootLike*\") -or" ^
  "    (($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and $_.CommandLine -match '-m\s+backend' -and $_.CommandLine -like \"*$rootLike*\") -or" ^
  "    (($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and $_.CommandLine -like '*doc_search.py*' -and $_.CommandLine -like \"*$rootLike*\") -or" ^
  "    ($_.Name -eq 'node.exe' -and $_.CommandLine -like \"*$rootLike*\\electron*\")" ^
  "  )" ^
  "} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue };" ^
  "foreach ($p in @($port, $dbPort)) {" ^
  "  try {" ^
  "    Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | ForEach-Object {" ^
  "      Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue" ^
  "    }" ^
  "  } catch {}" ^
  "};" ^
  "Start-Sleep -Milliseconds 400;" ^
  "$left = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue;" ^
  "if ($left) { Write-Host ('[警告] 端口 {0} 仍被 PID {1} 占用' -f $port, ($left | Select-Object -First 1).OwningProcess) }" ^
  "else { Write-Host ('[易知] 端口 {0} 已就绪' -f $port) };" ^
  "$leftDb = Get-NetTCPConnection -LocalPort $dbPort -State Listen -ErrorAction SilentlyContinue;" ^
  "if ($leftDb) { Write-Host ('[警告] DocuBrowser 端口 {0} 仍被 PID {1} 占用' -f $dbPort, ($leftDb | Select-Object -First 1).OwningProcess) }"

ping -n 2 127.0.0.1 >nul
endlocal
exit /b 0
