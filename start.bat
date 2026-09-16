@echo off
REM CodePilot Remote - start the desktop server (API + web dashboard) on Windows.
setlocal

cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
  echo [CodePilot] Python was not found on PATH.
  echo             Install Python 3.10 or newer from https://www.python.org/downloads/
  echo             and make sure "Add python.exe to PATH" is ticked.
  pause
  exit /b 1
)

if not exist "%~dp0server\.venv" (
  echo [CodePilot] Creating a virtual environment in server\.venv ...
  python -m venv "%~dp0server\.venv" || goto :fail
  "%~dp0server\.venv\Scripts\python.exe" -m pip install --upgrade pip >nul
  echo [CodePilot] Installing dependencies ...
  "%~dp0server\.venv\Scripts\python.exe" -m pip install -r "%~dp0server\requirements.txt" || goto :fail
)

cd /d "%~dp0server"
"%~dp0server\.venv\Scripts\python.exe" -m codepilot %*
goto :eof

:fail
echo [CodePilot] Setup failed. See the messages above.
pause
exit /b 1
