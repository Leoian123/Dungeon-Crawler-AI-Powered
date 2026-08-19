@echo off
REM ============================================================================
REM  gioca_web.bat - GIOCA dal browser: doppio click e parte tutto.
REM
REM  Default (un solo processo, una sola origine):
REM    1. se web\dist manca e npm esiste, COMPILA la SPA (npm run build);
REM    2. avvia l'host FastAPI (127.0.0.1:8017) che serve SPA compilata + API;
REM    3. apre il browser sul gioco.
REM
REM  Corsie:
REM    gioca_web.bat --dev             sviluppo: host in finestra + Vite (HMR)
REM                                    su http://localhost:5173 (proxy -> host)
REM    gioca_web.bat --fake            vieta il GM live per l'intero processo
REM    gioca_web.bat --porta N         porta alternativa (browser incluso)
REM    gioca_web.bat --senza-browser   non aprire il browser (editor/preview)
REM
REM  GM: la scelta fake/live avviene alla CREAZIONE della partita via API. Un
REM  processo = UNA partita (World esper process-global): per ricominciare,
REM  riavvia. CHIAVE API (PLK par.4): vive SOLO nell'ambiente o in un .env
REM  locale gitignored; questo launcher carica .env SENZA stamparla e la chiave
REM  non passa MAI per argomenti, URL, log, o verso il browser.
REM ============================================================================
setlocal
chcp 65001 >nul

cd /d "%~dp0"
set "PYTHONPATH=%~dp0src;%~dp0vendor"

REM --- Segreti locali: carica .env (se esiste) nell'ambiente, senza echo ------
REM (PRIMA della delayed expansion: un valore con '!' non va corrotto.)
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

REM --- Argomenti: corsia dev, apertura browser, porta; il resto va all'host ---
setlocal enabledelayedexpansion
set "MODO_DEV="
set "APRI_BROWSER=1"
set "PORTA=8017"
set "ARGS_HOST="
set "ATTESA_PORTA="
for %%x in (%*) do (
    if /i "%%x"=="--dev" (
        set "MODO_DEV=1"
    ) else if /i "%%x"=="--senza-browser" (
        set "APRI_BROWSER="
    ) else (
        if defined ATTESA_PORTA (
            set "PORTA=%%x"
            set "ATTESA_PORTA="
        )
        if /i "%%x"=="--porta" set "ATTESA_PORTA=1"
        set "ARGS_HOST=!ARGS_HOST! %%x"
    )
)

if defined MODO_DEV goto :dev

REM --- Corsia PRODOTTO: SPA compilata servita dall'host (una origine) ---------
if not exist "web\dist\index.html" (
    where npm >nul 2>&1
    if errorlevel 1 (
        echo [gioca_web] SPA non compilata ^(web\dist assente^) e npm non trovato.
        echo [gioca_web] Installa Node e lancia:   npm --prefix web run build
        echo [gioca_web] Avvio comunque l'host API-only su http://127.0.0.1:!PORTA!/api
    ) else (
        echo [gioca_web] Prima compilazione della SPA ^(solo la prima volta^)...
        if not exist "web\node_modules" call npm --prefix web install
        call npm --prefix web run build
        if errorlevel 1 echo [gioca_web] Build fallita: avvio l'host API-only.
    )
)

if defined APRI_BROWSER (
    REM Si apre da solo appena l'host ha fatto il bind (2s bastano in locale).
    start "" /min cmd /c "timeout /t 2 >nul & start http://127.0.0.1:!PORTA!/"
)

echo [gioca_web] Avvio del gioco su http://127.0.0.1:!PORTA! ...
"%PY%" -m host_web!ARGS_HOST!
goto :fine

REM --- Corsia DEV: host in finestra separata + Vite con HMR -------------------
:dev
where npm >nul 2>&1
if errorlevel 1 (
    echo [gioca_web] La corsia --dev richiede Node/npm ^(Vite^).
    exit /b 1
)
if not exist "web\node_modules" call npm --prefix web install
echo [gioca_web] Host API in finestra separata su http://127.0.0.1:!PORTA! ...
start "DCC host web" cmd /k ""%PY%" -m host_web!ARGS_HOST!"
if defined APRI_BROWSER (
    start "" /min cmd /c "timeout /t 3 >nul & start http://localhost:5173/"
)
echo [gioca_web] Vite dev server ^(HMR^) su http://localhost:5173 ...
set "DCC_API_PORT=!PORTA!"
call npm --prefix web run dev

:fine
endlocal
endlocal
