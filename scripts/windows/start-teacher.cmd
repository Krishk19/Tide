@echo off
rem Starts the Tide teacher server.
rem The first time, it asks Windows for admin once to open the firewall for students.
rem Usage: start-teacher.cmd [--mock]
setlocal
cd /d "%~dp0..\.."

if not exist ".venv\Scripts\tide-server.exe" (
  echo.
  echo   Tide is not set up on this PC yet.
  echo   Double-click  "TEACHER - 1 Setup (once).bat"  first.
  echo.
  pause
  exit /b 1
)

set "RULES=yes"
netsh advfirewall firewall show rule name="Tide server" >nul 2>&1 || set "RULES=no"
netsh advfirewall firewall show rule name="Tide discovery" >nul 2>&1 || set "RULES=no"

if "%RULES%"=="no" (
  net session >nul 2>&1
  if errorlevel 1 (
    echo Asking Windows for permission to let students connect ^(first time only^)...
    if "%~1"=="" (
      powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    ) else (
      powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%*' -Verb RunAs"
    )
    exit /b
  )
  netsh advfirewall firewall add rule name="Tide server" dir=in action=allow protocol=TCP localport=8765 profile=any >nul
  netsh advfirewall firewall add rule name="Tide discovery" dir=in action=allow protocol=UDP localport=47800 profile=any >nul
  echo Firewall opened for Tide ^(ports 8765 and 47800^).
)

cd /d "%~dp0..\.."
title Tide - TEACHER  (keep this window open)
".venv\Scripts\tide-server.exe" --fresh %*
echo.
echo   Tide stopped.
pause
