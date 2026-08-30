@echo off
REM Qoresence one-liner launcher for Windows
REM Usage: qoresence.bat [--play] [--deck] [--monitor] [--tray] [other args]
REM
REM Double-click to start with defaults: --play --deck --monitor --tray --a2a
REM Or pass custom args: qoresence.bat --play --deck --streamer-fps 60

setlocal

REM Change to the Qoresence directory (where this script lives)
cd /d "%~dp0"
REM Git tree wins over a stale pip install of qoresence.
set PYTHONPATH=%~dp0;%PYTHONPATH%

REM Activate venv if present
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

REM Enable A2A reasoning tier (Gemini scene + DeepSeek chat agents)
set QORESENCE_A2A=1
set QORESENCE_A2A_GEMINI=1
set QORESENCE_A2A_DEEPSEEK=1
REM Match-observer on this launcher only. --play in Python stays default OFF.
REM Unlicensed / no key still paints the empty Clutch Feed line.
set QORESENCE_MATCH_AGENT=1
REM AgentGlass spectator API — default OFF, enable with QORESENCE_AGENT_GLASS_ENABLED=1
REM Example: set QORESENCE_AGENT_GLASS_ENABLED=1 & python -m qoresence.cli --play --deck --agent-glass

REM If no args passed, use sensible defaults
if "%~1"=="" (
    echo Starting Qoresence with defaults: --play --deck --monitor --tray --a2a --controller
    echo MatchAgent: QORESENCE_MATCH_AGENT=1 (lobe still default-OFF without this launcher)
    echo Game profile: last pin / QORESENCE_GAME_PROFILE / first-run ncaa_football_27
    python -c "import qoresence, pathlib; print('qoresence from', pathlib.Path(qoresence.__file__).resolve())"
    python -m qoresence.cli --play --deck --monitor --tray --a2a --controller --streamer-fps 60
) else (
    python -c "import qoresence, pathlib; print('qoresence from', pathlib.Path(qoresence.__file__).resolve())"
    python -m qoresence.cli %*
)

endlocal
