@echo off
REM ============================================================================
REM  genera_stagione.bat - authoring AI del piano-mondo (strumento, NON gioco).
REM
REM  Genera i boss nominati (provincia, citta'), le tabelle procedurali e le
REM  tabelle di spawn della stagione. Ogni item passa dai lint del motore e da
REM  `risolvi_stagione` PRIMA di toccare la libreria; un item respinto viene
REM  scartato e riportato. Il diff git e' la promozione umana.
REM
REM  Uso:
REM    genera_stagione.bat                      (dry-run: genera e RIPORTA, zero scritture)
REM    genera_stagione.bat --applica            (scrive mob + piano nel repo)
REM    genera_stagione.bat --provincia 10 --citta 40
REM    genera_stagione.bat --fake               (smoke offline: 0 generati)
REM
REM  CHIAVE API (PLK par.4): serve ANTHROPIC_API_KEY nell'ambiente o in un .env
REM  LOCALE (gitignored; template: .env.example). Questo launcher carica .env
REM  SENZA stamparla; la chiave non passa MAI per argomenti, URL, log o repo.
REM  Senza chiave il comando lo dice e resta offline (nessun degrado muto).
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

"%PY%" -m genera_stagione %*

endlocal
