@echo off
where wt.exe >nul 2>&1
if not errorlevel 1 (
    start "" wt.exe -w new --maximized powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_download.ps1" %*
    exit /b
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_download.ps1" %*
pause
