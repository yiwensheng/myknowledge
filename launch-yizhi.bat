@echo off
setlocal EnableExtensions
set "RC=0"
chcp 65001 >nul 2>&1

REM YiZhi GUI launcher (Electron + Python API)
REM Entry: launch-yizhi.bat | 启动易知.bat | 启动Myknowledge.bat

set "MYK_ROOT=%~dp0"
set "MYK_ROOT=%MYK_ROOT:~0,-1%"
set "PYTHONIOENCODING=utf-8"

if defined YIZHI_INSTALLED (
  set "WIKI_ROOT=%LOCALAPPDATA%\Yizhi"
  set "MYKNOWLEDGE_ROOT=%WIKI_ROOT%"
) else (
  set "WIKI_ROOT=%MYK_ROOT%"
  set "MYKNOWLEDGE_ROOT=%MYK_ROOT%"
)

cd /d "%MYK_ROOT%"

if not defined YIZHI_PRE_CLEAN call "%MYK_ROOT%\stop-yizhi.bat"
set "YIZHI_PRE_CLEAN="

set "BUNDLED_MODE=0"
if defined YIZHI_PORTABLE set "BUNDLED_MODE=1"
if defined YIZHI_INSTALLED set "BUNDLED_MODE=1"

if "%BUNDLED_MODE%"=="1" (
  set "PATH=%MYK_ROOT%\python;%MYK_ROOT%\python\Scripts;%MYK_ROOT%\third_party\ffmpeg\bin;%MYK_ROOT%\third_party\bun;%PATH%"
) else (
  REM Source-tree launch: show backend logs in the console; do not treat as install layout.
  if not defined YIZHI_DEV set "YIZHI_DEV=1"
)

echo.
echo [易知] 正在启动图形界面...
echo [易知] 知识库目录: %WIKI_ROOT%
echo.

set "PYTHON_EXE="
if exist "%MYK_ROOT%\python\python.exe" (
  set "PYTHON_EXE=%MYK_ROOT%\python\python.exe"
) else if exist "%MYK_ROOT%\python\Scripts\python.exe" (
  set "PYTHON_EXE=%MYK_ROOT%\python\Scripts\python.exe"
) else if "%BUNDLED_MODE%"=="1" (
  echo [错误] 内置 Python 缺失或损坏。请重新安装易知，勿依赖本机 Python。
  set "RC=1"
  goto :fail
) else (
  where python >nul 2>&1
  if errorlevel 1 (
    echo [错误] 未找到 python。请使用官方安装包，或安装 Python 3.10+ 并加入 PATH。
    set "RC=1"
    goto :fail
  )
  set "PYTHON_EXE=python"
)

if "%BUNDLED_MODE%"=="1" (
  "%PYTHON_EXE%" -c "import fastapi, uvicorn" >nul 2>&1
  if errorlevel 1 (
    echo [错误] 内置 Python 依赖不完整。请重新安装易知，勿在本机执行 pip install。
    set "RC=1"
    goto :fail
  )
) else (
  "%PYTHON_EXE%" -c "import fastapi, uvicorn" >nul 2>&1
  if errorlevel 1 (
    echo [提示] 首次使用需安装 Python 依赖，正在执行 pip install ...
    "%PYTHON_EXE%" -m pip install -r "%MYK_ROOT%\requirements.txt"
    if errorlevel 1 (
      echo [错误] pip install 失败，请手动运行: pip install -r requirements.txt
      set "RC=1"
      goto :fail
    )
  )
)

echo [易知] 检查内置 DocuBrowser ...
"%PYTHON_EXE%" "%MYK_ROOT%\scripts\setup_docubrowser.py"
if errorlevel 1 (
  echo [警告] DocuBrowser 安装未完成，批量文档检索可能不可用。
)

if not exist "%WIKI_ROOT%\" mkdir "%WIKI_ROOT%" 2>nul

if not exist "%WIKI_ROOT%\.env" (
  if exist "%MYK_ROOT%\.env.user" (
    echo [提示] 未找到 .env ，已从 .env.user 复制
    copy /Y "%MYK_ROOT%\.env.user" "%WIKI_ROOT%\.env" >nul
  ) else if exist "%MYK_ROOT%\.env.example" (
    echo [提示] 未找到 .env ，已从 .env.example 复制
    copy /Y "%MYK_ROOT%\.env.example" "%WIKI_ROOT%\.env" >nul
  )
)

if not exist "%WIKI_ROOT%\inbox\" (
  echo [提示] 首次运行，正在初始化目录...
  "%PYTHON_EXE%" -m lib.cli init
)

cd /d "%MYK_ROOT%\electron"
if not exist "node_modules\electron\dist\electron.exe" (
  if "%BUNDLED_MODE%"=="1" (
    echo [错误] 内置 Electron 缺失。请重新安装易知，勿依赖本机 Node.js。
    set "RC=1"
    goto :fail
  )
  if not exist "node_modules\electron\" (
    echo [易知] 首次运行，正在 npm install 仅需一次 ...
    call npm install
    if errorlevel 1 (
      echo [错误] npm install 失败。请确认已安装 Node.js。
      set "RC=1"
      goto :fail
    )
  )
)

rem Runtime needs renderer/vendor only; @file-viewer in node_modules is for sync.
rem If vendor already exists, skip npm to avoid EBUSY renaming locked electron default_app.asar.
if not exist "renderer\vendor\file-viewer\flyfish-file-viewer-web-full.iife.js" (
  if "%BUNDLED_MODE%"=="1" (
    echo [错误] File-Viewer 资源缺失。请重新安装易知。
    set "RC=1"
    goto :fail
  )
  if not exist "node_modules\@file-viewer\web-full\" (
    echo [易知] 正在安装文件预览依赖 @file-viewer/web-full ...
    rem Install preview package only; do not full npm install while electron is locked
    call npm install @file-viewer/web-full@^2.1.23 --save-dev --no-audit --no-fund --prefer-offline
    if errorlevel 1 (
      echo [错误] npm install @file-viewer/web-full 失败。
      echo 若报 EBUSY：请先关闭所有 Electron/易知窗口，再执行:
      echo   cd /d "%MYK_ROOT%\electron"
      echo   move node_modules\electron node_modules\electron._bak
      echo   npm install @file-viewer/web-full@^2.1.23 --save-dev --no-audit --no-fund
      echo   move node_modules\electron._bak node_modules\electron
      set "RC=1"
      goto :fail
    )
  )
  echo [易知] 同步本地文件预览组件 File-Viewer ...
  call npm run sync-file-viewer
  if errorlevel 1 (
    echo [错误] File-Viewer 同步失败。请手动运行: cd electron ^&^& npm run sync-file-viewer
    set "RC=1"
    goto :fail
  )
)

echo [易知] 启动 Electron ...

"node_modules\electron\dist\electron.exe" .
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :fail
exit /b 0

:fail
echo.
echo [易知] 启动失败，错误码: %RC%
if "%BUNDLED_MODE%"=="0" pause
exit /b 1
