@echo off
rem Installs the boot guard: autologin stays on, but a normal power-on locks the PC again.
rem Only the phone wake (wake.py on the Raspberry Pi) skips the lock.
setlocal
set /p URL=Adresse des Wake-Relays (z.B. http://192.168.1.50:8766): 
set /p TOK=Token des Relays (steht beim Start von wake.py in der URL nach dem #): 
for /f "delims=" %%i in ('py -c "import sys;print(sys.executable.replace('python.exe','pythonw.exe'))"') do set PYW=%%i
if not exist "%PYW%" (
  echo Python nicht gefunden.
  pause
  exit /b 1
)
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
echo CreateObject("WScript.Shell").Run """%PYW%"" ""%~dp0boot_guard.py"" --url ""%URL%"" --token ""%TOK%""", 0, False> "%STARTUP%\PCRemoteGuard.vbs"
echo Fertig. Ab jetzt: Anschalten vom Handy = direkt Desktop, Powertaste = Passwort noetig.
pause
