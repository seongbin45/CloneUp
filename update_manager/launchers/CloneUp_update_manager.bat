@echo off
REM CloneUp update manager — console-friendly fallback.
REM Login / Scheduled Task should use CloneUp_update_manager_hidden.vbs instead
REM so no black console window appears.
set "DIR=%~dp0"
if exist "%DIR%CloneUp_update_manager.exe" (
  start "" /B "%DIR%CloneUp_update_manager.exe" %*
) else (
  exit /b 1
)
