@echo off
setlocal

rem ===========================================================================
rem  Rem Downloader - launcher (double-click this file)
rem
rem  This file is intentionally ASCII-only: cmd.exe renders its own output with
rem  the OEM code page, so non-ASCII text here could turn into garbled
rem  characters. All user-facing messages live in the PowerShell scripts, which
rem  switch the console to UTF-8 themselves.
rem
rem  Dependencies are checked automatically on startup; missing ones are
rem  installed by launch_download.ps1. On failure the window stays open so the
rem  message can be read.
rem ===========================================================================

set "REM_LAUNCHER=%~dp0launch_download.ps1"

if not exist "%REM_LAUNCHER%" (
    echo [ERROR] launch_download.ps1 was not found:
    echo         %REM_LAUNCHER%
    echo.
    echo Please keep all Rem Downloader files in the same folder.
    pause
    exit /b 1
)

rem Prefer Windows Terminal: the app is a full-screen terminal UI.
where wt.exe >nul 2>&1
if not errorlevel 1 (
    start "" wt.exe -w new --maximized powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%REM_LAUNCHER%" %*
    if not errorlevel 1 exit /b 0
)

rem Fallback: run in the current console window.
rem launch_download.ps1 waits for a key press on failure, so the window will
rem not vanish before the user can read the message.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%REM_LAUNCHER%" %*
exit /b %ERRORLEVEL%
