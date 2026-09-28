@echo off
rem Starts the Tide student agent. No admin needed.
setlocal
cd /d "%~dp0..\.."
if not exist ".venv\Scripts\tide-agent.exe" (
  echo.
  echo   Tide is not set up on this PC yet.
  echo   Double-click  "STUDENT - 1 Setup (once).bat"  first.
  echo.
  pause
  exit /b 1
)
title Tide - STUDENT  (keep this window open)
".venv\Scripts\tide-agent.exe" %*
