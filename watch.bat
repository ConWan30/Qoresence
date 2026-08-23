@echo off
REM Start Deck if it is down, then watch /health while you play.
REM This machine only: http://127.0.0.1:8765  (no 0.0.0.0)

setlocal
cd /d "%~dp0"
set PYTHONPATH=%~dp0;%PYTHONPATH%
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"

python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=2)" 1>nul 2>nul
if errorlevel 1 (
    echo Starting Qoresence --play --deck --streamer-fps 60
    start "Qoresence Deck" cmd /k ""%~dp0qoresence.bat" --play --deck --streamer-fps 60"
    echo Waiting for Theater...
    timeout /t 12 /nobreak >nul
)

echo.
echo Theater  http://127.0.0.1:8765/deck.html
echo Health   http://127.0.0.1:8765/health
echo Watchdog: age_s under 1.0 and frames/pushes climbing is healthy.
echo Ctrl+C stops the watchdog only. Close the Qoresence Deck window to stop capture.
echo.
python scripts\session_watchdog.py --interval 3
endlocal
