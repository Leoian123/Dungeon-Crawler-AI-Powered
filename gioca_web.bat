@echo off
REM ============================================================================
REM  gioca_web.bat - avvia l'HOST WEB di gioco (API FastAPI su 127.0.0.1:8017).
REM
REM  Host opt-in fuori dal motore (src/host_web): mappa le porte di SessioneGioco
REM  su endpoint HTTP + SSE. Il frontend e' la SPA React in web/ (in sviluppo:
REM  cd web && npm run dev -> http://localhost:5173, proxy /api verso 8017).
REM
REM  GM: la scelta fake/live avviene alla CREAZIONE della partita via API; il
REM  flag --fake qui vieta il live per l'intero processo. Un processo = UNA
REM  partita (World esper process-global): per ricominciare, riavvia.
REM
REM  CHIAVE API (PLK par.4): la chiave vive SOLO nell'ambiente o in un .env
REM  LOCALE (gitignored). Questo launcher carica .env SENZA stamparla; la chiave
REM  non passa MAI per argomenti, URL, log, o verso il browser.
REM ============================================================================
setlocal
chcp 65001 >nul

cd /d "%~dp0"
set "PYTHONPATH=%~dp0src;%~dp0vendor"

REM --- Segreti locali: carica .env (se esiste) nell'ambiente, senza echo ------
if exist ".env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do (
        if not "%%b"=="" set "%%a=%%b"
    )
)

REM Python del venv se presente (creato da start.bat), altrimenti quello di sistema.
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

REM FastAPI/uvicorn sono requisiti dell'host web (pinnati in requirements.txt).
"%PY%" -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
    echo [gioca_web] FastAPI/uvicorn non installati nell'ambiente Python in uso.
    echo [gioca_web] Installali con:   "%PY%" -m pip install -r requirements.txt
    exit /b 1
)

echo [gioca_web] Avvio dell'host web di gioco...
"%PY%" -m host_web %*

endlocal
