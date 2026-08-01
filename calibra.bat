@echo off
REM ============================================================================
REM  calibra.bat - console di calibrazione WEB (a un click, si apre nel browser).
REM
REM  Distribuisce e calibra la parte numerica del gioco senza toccare il codice:
REM  profili per-entita' dei nemici (statistiche + geometria + resistenze) e
REM  coefficienti globali §11, ognuno con la spiegazione del proprio impatto.
REM
REM  esper e' VENDORIZZATO (vendor/esper): PYTHONPATH include src e vendor.
REM  Gli override finiscono in src\motore\calibrazione.overrides.json (gitignored)
REM  e valgono dal prossimo avvio del motore. Chiudi con Ctrl-C nella finestra.
REM ============================================================================
setlocal
chcp 65001 >nul

cd /d "%~dp0"
set "PYTHONPATH=%~dp0src;%~dp0vendor"

REM Python del venv se presente (creato da start.bat), altrimenti quello di sistema.
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo [calibra] Avvio della console web... il browser si aprira' da solo.
"%PY%" -m calibratore_web %*

endlocal
