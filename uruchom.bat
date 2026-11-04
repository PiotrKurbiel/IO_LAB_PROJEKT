@echo off
chcp 65001 >nul
title LangChat - uruchamianie
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Brak srodowiska .venv - najpierw uruchom instalacja.bat
    pause
    exit /b 1
)

findstr /r /c:"^GOOGLE_API_KEY=..*" .env >nul 2>&1
if errorlevel 1 (
    echo UWAGA: brak klucza Gemini w pliku .env - bot nie będzie odpowiadał.
    echo Wklej klucz z https://aistudio.google.com/apikey jako GOOGLE_API_KEY=...
    echo.
)

echo [1/4] Docker...
docker info >nul 2>&1
if not errorlevel 1 goto docker_ok
echo Docker Desktop nie działa - uruchamiam go (to może potrwać do minuty)...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
set /a proby=0
:czekaj_docker
ping -n 3 127.0.0.1 >nul
docker info >nul 2>&1
if not errorlevel 1 goto docker_ok
set /a proby+=1
if %proby% lss 60 goto czekaj_docker
echo Docker nie wstał. Uruchom Docker Desktop ręcznie z menu Start i odpal ten plik jeszcze raz.
pause
exit /b 1
:docker_ok

echo [2/4] Baza danych...
docker start projekt_lab_db >nul 2>&1
if not errorlevel 1 goto baza_start
echo Brak kontenera - tworzę bazę projekt_lab...
docker run -d --name projekt_lab_db -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=projekt_lab -p 5432:5432 postgres:17
if errorlevel 1 (
    echo Nie udało się utworzyć bazy.
    pause
    exit /b 1
)
:baza_start
set /a proby=0
:czekaj_baza
docker exec projekt_lab_db pg_isready -U postgres >nul 2>&1
if not errorlevel 1 goto baza_ok
set /a proby+=1
if %proby% geq 30 goto baza_blad
ping -n 2 127.0.0.1 >nul
goto czekaj_baza
:baza_blad
echo Baza nie odpowiada - sprawdź kontener projekt_lab_db w Docker Desktop.
pause
exit /b 1
:baza_ok

echo [3/4] Backend i frontend - otwierają się w osobnych oknach, nie zamykaj ich podczas pracy...
start "LangChat - backend" cmd /k ".venv\Scripts\uvicorn.exe main:app --port 8000"
start "LangChat - frontend" cmd /k ".venv\Scripts\streamlit.exe run app.py --server.port 8501 --server.headless true"

echo [4/4] Czekam, aż aplikacja wstanie...
set /a proby=0
:czekaj_app
ping -n 2 127.0.0.1 >nul
curl.exe -s -o nul http://127.0.0.1:8000/docs && curl.exe -s -o nul http://127.0.0.1:8501 && goto app_ok
set /a proby+=1
if %proby% lss 60 goto czekaj_app
echo Aplikacja nie wstała - sprawdź komunikaty w oknach backend i frontend.
pause
exit /b 1
:app_ok
start "" http://localhost:8501
echo.
echo Gotowe! Aplikacja działa pod adresem http://localhost:8501
echo Żeby wszystko wyłączyć, uruchom zatrzymaj.bat
ping -n 6 127.0.0.1 >nul
