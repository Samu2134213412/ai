@echo off
chcp 65001 >nul
title PC Remote - Server (Fenster offen lassen)
cd /d "%~dp0"
echo.
echo  PC Remote wird gestartet. Dieses Fenster offen lassen (zum Beenden schliessen).
echo  Den Link zum Oeffnen am Handy zeigt danach LINK-ANZEIGEN.bat
echo.
py server.py
echo.
echo  Fehler beim Start. Bitte Foto von diesem Fenster machen.
pause
