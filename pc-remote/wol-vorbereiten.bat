@echo off
chcp 65001 >nul
title PC fuer Anschalten per Handy vorbereiten
net session >nul 2>&1
if errorlevel 1 (
  echo Es werden Administrator-Rechte gebraucht. Bitte mit JA bestaetigen ...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
echo.
echo  Netzwerkkarten werden fuer "Aufwecken per Netzwerk" vorbereitet ...
powershell -NoProfile -Command "Get-NetAdapter -Physical | ForEach-Object { try { Set-NetAdapterPowerManagement -Name $_.Name -WakeOnMagicPacket Enabled -WakeOnPattern Disabled -ErrorAction Stop; Write-Host ('OK: ' + $_.Name + '  MAC ' + $_.MacAddress) } catch { Write-Host ('uebersprungen: ' + $_.Name) } }"
echo.
echo  Windows-Schnellstart wird ausgeschaltet (sonst klappt Aufwecken oft nicht) ...
powercfg /h off
echo.
echo  ============================================================
echo   FERTIG. Noch EINMAL von Hand noetig (je nach PC verschieden):
echo   Im BIOS/UEFI "Wake on LAN" bzw. "Power on by PCI-E" einschalten.
echo   Der PC muss mit LAN-KABEL am Router haengen (WLAN geht meist nicht).
echo  ============================================================
pause
