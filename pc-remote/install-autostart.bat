@echo off
rem Starts PC Remote automatically (hidden) every time you log in to Windows.
setlocal
for /f "delims=" %%i in ('py -c "import sys;print(sys.executable.replace('python.exe','pythonw.exe'))"') do set PYW=%%i
if not exist "%PYW%" (echo Python nicht gefunden. Erst Python installieren. & pause & exit /b 1)
schtasks /Create /TN "PC Remote" /TR "\"%PYW%\" \"%~dp0server.py\"" /SC ONLOGON /F
if errorlevel 1 (echo Fehler beim Anlegen der Aufgabe. & pause & exit /b 1)
schtasks /Run /TN "PC Remote" >nul
echo.
echo Fertig. PC Remote startet jetzt bei jeder Windows-Anmeldung von selbst.
echo Tipp: Windows-Autologin einrichten (Win+R, netplwiz), damit der PC nach dem
echo Anschalten ohne PIN-Eingabe hochfaehrt.
pause
