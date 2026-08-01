@echo off
REM ============================================================================
REM  gioca.bat - avvia il gioco con l'interfaccia Textual (a un click).
REM
REM  UI di gioco (host, fuori dal motore): pilota il game engine via le porte di
REM  SessioneGioco. Esplorazione sulla mappa del piano, interattiva:
REM    narrazione della stanza -> Combatti/Scappi (se c'e' un nemico)
REM    -> combattimento a turni (Attacca) -> Vai: stanza N / Scendi la scala
REM    -> discesa = vittoria del piano (MVP). Comandi: click; 's' salva; 'q' esce.
REM
REM  Provider OFFLINE (FakeProvider): nessuna chiave LLM, nessuna rete.
REM  esper e' VENDORIZZATO (vendor/esper): PYTHONPATH include src e vendor.
REM
REM  ATTENZIONE: Textual NON e' una dipendenza del progetto (il motore e' headless)
REM  e NON viene installato da start.bat. Questo launcher lo verifica e, se manca,
REM  ti dice come installarlo nel venv.
REM ============================================================================
setlocal
chcp 65001 >nul

cd /d "%~dp0"
set "PYTHONPATH=%~dp0src;%~dp0vendor"

REM Python del venv se presente (creato da start.bat), altrimenti quello di sistema.
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

REM Textual e' un requisito SOLO di questo host opzionale: verifica esplicita.
"%PY%" -c "import textual" >nul 2>&1
if errorlevel 1 (
    echo [gioca] Textual non e' installato nell'ambiente Python in uso.
    echo [gioca] Installalo con:   "%PY%" -m pip install textual
    echo [gioca] ^(Textual resta fuori da requirements: e' un host opt-in, il motore e' headless.^)
    exit /b 1
)

echo [gioca] Avvio dell'interfaccia di gioco Textual...
"%PY%" -m gioco_textual %*

endlocal
