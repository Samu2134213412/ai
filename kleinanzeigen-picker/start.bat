@echo off
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 (
  echo Node.js fehlt. Bitte von https://nodejs.org installieren ^(LTS^) und erneut starten.
  pause
  exit /b 1
)
node server.js --open
pause
