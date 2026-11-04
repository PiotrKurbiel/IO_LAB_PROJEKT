@echo off
chcp 65001 >nul
title LangChat - instalacja
cd /d "%~dp0"

echo [1/3] Środowisko Pythona .venv...
if exist ".venv\Scripts\python.exe" goto venv_ok
py -3.13 -m venv .venv 2>nul || py -3 -m venv .venv
if not exist ".venv\Scripts\python.exe" (
    echo Nie znaleziono Pythona - zainstaluj Python 3.13 z python.org i uruchom ten plik ponownie.
    pause
    exit /b 1
)
:venv_ok

echo [2/3] Biblioteki z requirements.1...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.1
if errorlevel 1 (
    echo Instalacja bibliotek nie powiodła się.
    pause
    exit /b 1
)

echo [3/3] Plik .env z kluczem API...
if exist ".env" goto env_ok
(echo GOOGLE_API_KEY=)>.env
echo Utworzono plik .env - wklej do niego klucz z https://aistudio.google.com/apikey
:env_ok

echo.
echo Instalacja zakończona. Aplikację uruchamiasz plikiem uruchom.bat
pause
