@echo off
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\PCRemote.vbs" 2>nul
taskkill /IM pythonw.exe /F >nul 2>&1
echo Autostart entfernt.
pause
