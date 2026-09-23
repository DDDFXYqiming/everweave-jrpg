@echo off
pwsh -NoProfile -File "%~dp0Start.ps1" -Web %*
if errorlevel 1 pause
