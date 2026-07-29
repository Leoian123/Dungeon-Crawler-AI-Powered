@echo off
REM ============================================================================
REM  Banco di prova nemici - lancio da Windows.
REM
REM  Uso:
REM    banco_nemici.bat                                  (demo offline --fake)
REM    banco_nemici.bat --fake --livello 2 --seed 1
REM    banco_nemici.bat --livello 3 --seed 7 --contesto "Il corridoio..." ^
REM                     --modelli claude-opus-4-8 ^<altro-model-id^>
REM
REM  Il confronto live richiede la variabile d'ambiente ANTHROPIC_API_KEY.
REM ============================================================================
setlocal
chcp 65001 >nul

REM Radice del repo = cartella di questo .bat (con backslash finale).
set "REPO=%~dp0"
set "PYTHONPATH=%REPO%src;%REPO%vendor"

REM Python del venv se presente, altrimenti quello di sistema.
set "PY=%REPO%.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

if "%~1"=="" (
    echo [banco_nemici] nessun argomento: eseguo la demo offline ^(--fake^).
    echo Per il confronto live: banco_nemici.bat --livello 3 --modelli claude-opus-4-8 ^<altro-id^>
    echo.
    "%PY%" -m banco_nemici --fake --livello 2 --seed 1
    echo.
    pause
) else (
    "%PY%" -m banco_nemici %*
)

endlocal
