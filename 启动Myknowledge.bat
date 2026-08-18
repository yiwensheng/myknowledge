@echo off
cd /d "%~dp0"
REM 启动前先结束旧实例、释放 API 端口
call "%~dp0stop-yizhi.bat"
set "YIZHI_PRE_CLEAN=1"
call "%~dp0launch-yizhi.bat" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" pause
exit /b %RC%
