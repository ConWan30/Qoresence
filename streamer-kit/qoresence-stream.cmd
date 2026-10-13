@echo off
REM Qoresence Streamer Kit launcher (template). Copy next to qoresence.bat in your Qoresence checkout.
REM The obs-websocket password is NEVER stored in this file. Provide it one of two ways:
REM   1) set QORESENCE_OBS_PASSWORD in your user environment, or
REM   2) put it alone on the first line of %USERPROFILE%\.qoresence\obs_password.txt
REM      (override the path with QORESENCE_OBS_PASSWORD_FILE).
setlocal
if not defined QORESENCE_OBS_PASSWORD_FILE set "QORESENCE_OBS_PASSWORD_FILE=%USERPROFILE%\.qoresence\obs_password.txt"
if not defined QORESENCE_OBS_PASSWORD (
  if exist "%QORESENCE_OBS_PASSWORD_FILE%" (
    set /p QORESENCE_OBS_PASSWORD=<"%QORESENCE_OBS_PASSWORD_FILE%"
  )
)
if not defined QORESENCE_OBS_PASSWORD (
  echo [streamer-kit] No obs-websocket password found. Set QORESENCE_OBS_PASSWORD or create
  echo                %QORESENCE_OBS_PASSWORD_FILE%  ^(OBS: Tools ^> WebSocket Server Settings ^> Show Connect Info^)
  echo                Continuing: the bridge will only connect if OBS auth is disabled.
)
if not defined QORESENCE_OBS_PORT set "QORESENCE_OBS_PORT=4455"
REM Scene and text source names must match the imported scene collection.
REM OBS shares one name namespace for scenes and sources, so the text source is "Qoresence Score Text".
call "%~dp0qoresence.bat" --play --deck --monitor --tray --controller --streamer-fps 60 --obs --obs-text-source "Qoresence Score Text" %*
endlocal
