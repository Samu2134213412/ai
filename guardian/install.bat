@echo off
REM Guardian installieren: baut Guardian und richtet es fuer diesen Benutzer ein.
REM Was genau passiert, steht oben in install.ps1.
REM -ExecutionPolicy Bypass gilt nur fuer diesen einen Aufruf und aendert keine
REM Einstellung -- ohne das startet Windows lokale .ps1-Skripte oft gar nicht.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set RC=%ERRORLEVEL%
echo.
pause
exit /b %RC%
