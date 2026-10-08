@echo off
chcp 65001 >nul
title PC Remote - Einrichten
cd /d "%~dp0"
echo.
echo  ============================================
echo   Einrichten (nur einmal noetig, ca. 5 Min.)
echo  ============================================
echo.
py --version >nul 2>&1
if errorlevel 1 (
  echo  [1/3] Python wird installiert. Bitte mit JA bestaetigen, wenn Windows fragt ...
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  echo.
  echo  Python ist jetzt installiert. Bitte dieses Fenster SCHLIESSEN
  echo  und EINRICHTEN noch einmal doppelklicken.
  pause
  exit /b 0
)
echo  [1/3] Python ist da.
echo  [2/3] Programmteile werden geladen ...
py -m pip install --quiet -r requirements.txt
if errorlevel 1 goto fehler
echo  [3/3] Verbindungs-Werkzeug wird installiert ...
winget install -e --id Cloudflare.cloudflared --accept-source-agreements --accept-package-agreements
echo.
echo  ============================================
echo   FERTIG! Jetzt kannst du dieses Fenster schliessen.
echo   Wenn du Hilfe brauchst: HILFE-STARTEN doppelklicken.
echo  ============================================
pause
exit /b 0
:fehler
echo.
echo  Es hat etwas nicht geklappt. Bitte ein Foto von diesem Fenster machen
echo  und an die helfende Person schicken.
pause
exit /b 1
