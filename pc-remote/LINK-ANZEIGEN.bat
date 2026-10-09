@echo off
chcp 65001 >nul
cd /d "%~dp0"
py show_link.py
pause
