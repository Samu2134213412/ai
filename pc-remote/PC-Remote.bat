@echo off
rem Opens the PC Remote control panel (no console window).
cd /d "%~dp0"
start "" pythonw "%~dp0panel.pyw" 2>nul || start "" py "%~dp0panel.pyw"
