@echo off
REM ============================================================================
REM  misura_run.bat - misura della vincibilita' (STATO.md par.4.1): run
REM  automatiche via porte, OFFLINE (copione, mai rete), seeded.
REM
REM  Politiche x seed -> win-rate, profondita', scontri, drop, equip. E' lo
REM  strumento che rende falsificabile "il gioco e' vincibile giocando":
REM  due lanci identici producono gli stessi esiti.
REM
REM  Uso:
REM    misura_run.bat                                (tutte le politiche, 10 run)
REM    misura_run.bat --politiche combatti --run 20
REM    misura_run.bat --seed-base 100 --max-turni 600
REM    misura_run.bat --json esiti.json              (esiti per-run su file)
REM    misura_run.bat --live --json-oggetti raccolto.json
REM        (run generativa: GM live se c'e' la chiave; i template degli oggetti
REM         coniati in-run — descrizione inclusa — finiscono nel JSON)
REM
REM  Nessuna chiave API: la misura e' interamente offline e deterministica.
REM ============================================================================
setlocal
chcp 65001 >nul

cd /d "%~dp0"
set "PYTHONPATH=%~dp0src;%~dp0vendor"

REM --- Segreti locali: carica .env (se esiste) nell'ambiente, senza echo ------
REM  Serve SOLO a --live (la run generativa): il default resta offline e non
REM  tocca mai la rete. Stesso blocco di gioca.bat (PLK par.4: mai in argv/log).
if exist ".env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do (
        if not "%%b"=="" set "%%a=%%b"
    )
)

REM Python del venv se presente (creato da start.bat), altrimenti quello di sistema.
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" -m misura_run %*

endlocal
