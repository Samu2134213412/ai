@echo off
rem Doppelklick: legt Tutor-Ordner und Tutor.exe auf den Desktop (siehe install.ps1)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
pause
