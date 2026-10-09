@echo off
rem Opens the PC Remote control panel (no console window).
cd /d "%~dp0"
start "" pyw "%~dp0panel.pyw"
