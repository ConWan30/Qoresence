@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Qoresence is not installed yet.
    echo Run: powershell -ExecutionPolicy Bypass -File .\Install-Qoresence.ps1
    exit /b 1
)
call .venv\Scripts\activate.bat
REM Match-observer on this launcher only. --play in Python stays default OFF.
set QORESENCE_MATCH_AGENT=1
python -m qoresence.cli --play --deck --monitor --agent-glass --streamer-fps 30
endlocal
