@echo off
rem Starts PC Remote automatically (hidden) at every Windows login. No admin rights needed.
setlocal
for /f "delims=" %%i in ('py -c "import sys;print(sys.executable.replace('python.exe','pythonw.exe'))"') do set PYW=%%i
if not exist "%PYW%" (
  echo Python nicht gefunden. Erst Python installieren.
  pause
  exit /b 1
)
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
echo CreateObject("WScript.Shell").Run """%PYW%"" ""%~dp0server.py""", 0, False> "%STARTUP%\PCRemote.vbs"
if not exist "%STARTUP%\PCRemote.vbs" (
  echo Fehler: Autostart-Datei konnte nicht angelegt werden.
  pause
  exit /b 1
)
start "" wscript "%STARTUP%\PCRemote.vbs"
echo Starte PC Remote im Hintergrund, bitte 5 Sekunden warten ...
timeout /t 5 /nobreak >nul
powershell -NoProfile -Command "try{(Invoke-WebRequest http://127.0.0.1:8765/ -UseBasicParsing -TimeoutSec 3).StatusCode|Out-Null;exit 0}catch{exit 1}"
if errorlevel 1 (
  echo.
  echo ACHTUNG: PC Remote laeuft NICHT. Fehlerprotokoll: %USERPROFILE%\.pc-remote.log
  echo Bitte den Inhalt dieser Datei oder ein Foto dieses Fensters schicken.
  pause
  exit /b 1
)
echo.
echo OK - PC Remote laeuft im Hintergrund und startet kuenftig bei jeder Anmeldung von selbst.
echo Wichtig: Einmal "py server.py" sichtbar starten und die Firewall-Frage mit "Zugriff zulassen" bestaetigen,
echo sonst blockiert Windows den Zugriff vom Handy.
echo Tipp: Windows-Autologin einrichten (Win+R, netplwiz), damit der PC nach dem
echo Anschalten ohne PIN-Eingabe hochfaehrt.
pause
