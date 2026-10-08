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
echo.
echo Fertig. PC Remote startet jetzt bei jeder Windows-Anmeldung von selbst.
echo Tipp: Windows-Autologin einrichten (Win+R, netplwiz), damit der PC nach dem
echo Anschalten ohne PIN-Eingabe hochfaehrt.
pause
