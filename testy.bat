@echo off
chcp 65001 >nul
title LangChat - testy
cd /d "%~dp0"

".venv\Scripts\python.exe" -m pytest -v
pause
