@echo off
chcp 65001 >nul
title LangChat - zatrzymywanie
cd /d "%~dp0"

echo Zatrzymuję backend i frontend...
rem Okna z uruchom.bat – szukane po komendzie, nie po tytule (w Windows Terminalu to karty jednego okna)
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'cmd.exe' -and $_.CommandLine -match 'uvicorn.exe main:app|streamlit.exe run app.py' } | ForEach-Object { taskkill /pid $_.ProcessId /t /f }" >nul 2>&1
rem Gdyby serwery były uruchomione inaczej – procesy nasłuchujące na portach 8000 i 8501
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":8000 .*LISTENING" /c:":8501 .*LISTENING"') do taskkill /pid %%p /t /f >nul 2>&1

echo Zatrzymuję bazę danych...
docker stop projekt_lab_db >nul 2>&1

echo Gotowe.
ping -n 3 127.0.0.1 >nul
