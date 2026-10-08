@echo off
schtasks /Delete /TN "PC Remote" /F
taskkill /IM pythonw.exe /F >nul 2>&1
echo Autostart entfernt.
pause
