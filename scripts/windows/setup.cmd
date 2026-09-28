@echo off
rem Tide one-time setup. Usage: setup.cmd teacher|student
setlocal
set "ROLE=%~1"
cd /d "%~dp0..\.."
title Tide - %ROLE% setup
echo.
echo   ==========================================
echo      Tide setup for the %ROLE% PC  (run once)
echo   ==========================================
echo.

call :findpy
if errorlevel 1 goto nopy
echo   [1/3] Python found: %PY%

if not exist ".venv\Scripts\python.exe" (
  echo   [2/3] Creating a private Python environment in .venv ...
  %PY% -m venv .venv
  if errorlevel 1 goto fail
) else (
  echo   [2/3] Python environment already exists.
)

echo   [3/3] Installing Tide (a few minutes the first time) ...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
if /i "%ROLE%"=="teacher" (
  ".venv\Scripts\python.exe" -m pip install --quiet -e common -e server
) else (
  ".venv\Scripts\python.exe" -m pip install --quiet -e common -e agent
)
if errorlevel 1 goto fail

if /i "%ROLE%"=="teacher" if not exist ".env.local" call :askkey

echo.
echo   Done. Next time just double-click:
if /i "%ROLE%"=="teacher" (
  echo       TEACHER - 2 Start.bat
) else (
  echo       STUDENT - 2 Start.bat
)
echo.
pause
exit /b 0

:askkey
echo.
echo   Tide uses Jev (via OpenRouter) to recognise unknown AI sites and apps.
set "KEY="
set /p "KEY=  Paste your OpenRouter API key, or just press Enter to skip: "
> ".env.local" echo OPENROUTER_API_KEY=%KEY%
if "%KEY%"=="" (
  echo   Skipped. Tide will use simple keyword checks. Add the key later in .env.local
) else (
  echo   Saved to .env.local
)
exit /b 0

:findpy
for %%V in (3.12 3.13) do (
  py -%%V -c "import sys" >nul 2>&1 && (set "PY=py -%%V" & exit /b 0)
)
python -c "import sys; sys.exit(0 if (3,12) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>&1 && (set "PY=python" & exit /b 0)
exit /b 1

:nopy
echo   Python 3.12 is not installed.
echo.
echo   1. The download page is opening now. Install "Python 3.12".
echo   2. In the installer, tick  "Add python.exe to PATH".
echo   3. Then double-click this setup file again.
start "" "https://www.python.org/downloads/release/python-3129/"
echo.
pause
exit /b 1

:fail
echo.
echo   Setup failed. Scroll up for the error, fix it, then run this file again.
echo   (Most common cause: no internet during setup.)
pause
exit /b 1
