@echo off
chcp 65001 >nul
title PC Remote - Hilfe laeuft (zum Beenden Fenster schliessen)
cd /d "%~dp0"
echo.
echo  ==================================================================
echo   HILFE-VERBINDUNG WIRD GESTARTET ... bitte ca. 20 Sekunden warten.
echo   Wenn der Link erscheint: Er wird automatisch kopiert.
echo   Fuege ihn dann in eine Nachricht ein und schicke ihn ab.
echo   ZUM BEENDEN: dieses Fenster mit dem X oben rechts schliessen.
echo  ==================================================================
echo.
py server.py --tunnel --reset-token
echo.
echo  Es ist ein Fehler aufgetreten. Bitte ein Foto von diesem Fenster
echo  machen und an die helfende Person schicken.
pause
