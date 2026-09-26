@echo off
REM Guardian deinstallieren: entfernt guardian.exe und den PATH-Eintrag.
REM Konfiguration, Protokoll und Quarantaene bleiben liegen (siehe install.ps1).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -Uninstall %*
set RC=%ERRORLEVEL%
echo.
pause
exit /b %RC%
