@echo off
REM Qoresence one-liner launcher for Windows
REM Usage: qoresence.bat [--play] [--deck] [--monitor] [--tray] [other args]
REM
REM Double-click to start with defaults: --play --deck --monitor --tray --a2a
REM Or pass custom args: qoresence.bat --play --deck --streamer-fps 30

setlocal

REM Change to the Qoresence directory (where this script lives)
cd /d "%~dp0"

REM Activate venv if present
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

REM Enable A2A reasoning tier (Gemini scene + DeepSeek chat agents)
set QORESENCE_A2A=1
set QORESENCE_A2A_GEMINI=1
set QORESENCE_A2A_DEEPSEEK=1
REM AgentGlass spectator API — default OFF, enable with QORESENCE_AGENT_GLASS_ENABLED=1
REM Example: set QORESENCE_AGENT_GLASS_ENABLED=1 & python -m qoresence.cli --play --deck --agent-glass

REM If no args passed, use sensible defaults
if "%~1"=="" (
    echo Starting Qoresence with defaults: --play --deck --monitor --tray --a2a --controller
    echo Game profile: last pin / QORESENCE_GAME_PROFILE / first-run ncaa_football_27
    python -m qoresence.cli --play --deck --monitor --tray --a2a --controller --streamer-fps 30
) else (
    python -m qoresence.cli %*
)

endlocal
