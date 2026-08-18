@echo off

setlocal EnableExtensions

chcp 65001 >nul 2>&1



REM 易知 CLI (yws) - ask / query / produce / ingest / watch

REM Examples: yws ask "question" | yws list | yws ingest | yws watch

REM Add to PATH: setx PATH "%PATH%;e:\app\Myknowledge"



set "MYK_ROOT=%~dp0"

set "MYK_ROOT=%MYK_ROOT:~0,-1%"

set "WIKI_ROOT=%MYK_ROOT%"

set "MYKNOWLEDGE_ROOT=%MYK_ROOT%"

set "PYTHONIOENCODING=utf-8"



cd /d "%MYK_ROOT%"

python -m lib.cli %*

exit /b %ERRORLEVEL%

