@echo off
REM ============================================================================
REM  start.bat - setup venv + demo headless a un click (driver di riferimento).
REM  Per GIOCARE con l'interfaccia usa gioca.bat; per calibrare, calibra.bat.
REM
REM  Al PRIMO avvio crea un virtualenv (.venv) e installa le dipendenze; dal
REM  secondo avvio in poi il venv c'e' gia' e parte subito.
REM
REM  esper e' VENDORIZZATO (vendor/esper), non installato da pip: per questo
REM  PYTHONPATH include sia src che vendor.
REM ============================================================================
setlocal

REM Esegui sempre dalla cartella del progetto (dove vive questo .bat).
cd /d "%~dp0"

set "VENV_DIR=.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

REM --- Crea il venv + installa le dipendenze SOLO se non esiste gia' ----------
if not exist "%VENV_PY%" (
    echo [start] Primo avvio: creo l'ambiente virtuale...
    REM Per forzare Python 3.12 (pinnato in .python-version) usa: py -3.12 -m venv "%VENV_DIR%"
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [start] ERRORE: impossibile creare il venv. Python e' installato e su PATH?
        exit /b 1
    )

    echo [start] Installo le dipendenze ^(pydantic, ...^): la prima volta richiede un po'.
    "%VENV_PY%" -m pip install --upgrade pip >nul 2>&1
    "%VENV_PY%" -m pip install -r requirements.lock
    if errorlevel 1 (
        echo [start] ERRORE: installazione delle dipendenze fallita.
        exit /b 1
    )
)

REM --- src (i package del progetto) + vendor (esper) su PYTHONPATH ------------
set "PYTHONPATH=%~dp0src;%~dp0vendor"

echo [start] Avvio del game engine headless ^(driver di riferimento: un incontro completo^)...
"%VENV_PY%" -m main

endlocal
