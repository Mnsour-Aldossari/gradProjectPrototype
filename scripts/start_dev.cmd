@echo off
rem Double-click to start the backend and the web dashboard; start_dev.ps1 says what it does.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_dev.ps1" %*
if errorlevel 1 pause
