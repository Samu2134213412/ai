@echo off
rem Starts SchulKI with all arguments passed through.
cd /d "%~dp0"
python schulki.py %*
