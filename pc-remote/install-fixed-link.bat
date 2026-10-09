@echo off
chcp 65001 >nul
title PC Remote - fester Link
cd /d "%~dp0"
set TS=%ProgramFiles%\Tailscale\tailscale.exe
echo.
echo  Fester oeffentlicher Link ueber Tailscale (kostenlos). Einmalig einrichten.
echo.
if not exist "%TS%" (
  echo  [1/3] Tailscale wird installiert ...
  winget install -e --id Tailscale.Tailscale --accept-source-agreements --accept-package-agreements
)
if not exist "%TS%" (
  echo  Tailscale konnte nicht installiert werden. Foto dieses Fensters schicken.
  pause
  exit /b 1
)
echo  [2/3] Anmelden: Es oeffnet sich der Browser. Mit Google/Microsoft-Konto anmelden.
"%TS%" up
echo.
echo  [3/3] Oeffentlichen Link einschalten ...
"%TS%" funnel --bg 8765
echo.
echo  Falls oben eine Internet-Adresse steht ("To enable Funnel/HTTPS visit ..."):
echo  diese im Browser oeffnen, dort "Enable" klicken, danach diese Datei NOCHMAL starten.
echo.
"%TS%" funnel status
echo.
echo  Wenn oben eine Adresse https://....ts.net steht, ist es fertig.
echo  Den Link samt Zugangscode zeigt LINK-ANZEIGEN.bat (steht auch im Handy-Browser dauerhaft).
pause
