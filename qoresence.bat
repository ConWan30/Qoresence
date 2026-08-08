@echo off
REM Qoresence one-liner launcher for Windows
REM Usage: qoresence.bat [--play] [--deck] [--monitor] [--tray] [other args]
REM
REM Double-click to start with defaults: --play --deck --monitor --tray
REM Or pass custom args: qoresence.bat --play --deck --streamer-fps 30

setlocal

REM Change to the Qoresence directory (where this script lives)
cd /d "%~dp0"

REM Activate venv if present
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

REM If no args passed, use sensible defaults
if "%~1"=="" (
    echo Starting Qoresence with defaults: --play --deck --monitor --tray
    python -m qoresence.cli --play --deck --monitor --tray --streamer-fps 60
) else (
    python -m qoresence.cli %*
)

endlocal
