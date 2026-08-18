@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0..\license-server"
if not exist ".env" if exist ".env.example" copy /Y ".env.example" ".env" >nul
python -m pip install -r requirements.txt -q
python -m app.main
