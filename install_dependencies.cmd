@echo off
setlocal

rem ===========================================================================
rem  Rem Downloader - dependency installer / repair
rem
rem  ASCII-only on purpose (see run.cmd for the reason). All messages come from
rem  install_dependencies.ps1, which switches the console to UTF-8 and pauses on
rem  failure so the report stays readable.
rem
rem  Run this only when you want to install dependencies explicitly.
rem  Double-clicking run.cmd also does this automatically when needed.
rem ===========================================================================

set "REM_INSTALLER=%~dp0install_dependencies.ps1"

if not exist "%REM_INSTALLER%" (
    echo [ERROR] install_dependencies.ps1 was not found:
    echo         %REM_INSTALLER%
    echo.
    echo Please keep all Rem Downloader files in the same folder.
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%REM_INSTALLER%"
exit /b %ERRORLEVEL%
