@echo off
rem Startet den PC Baukasten auf http://localhost:8080 (braucht Python oder Node).
cd /d "%~dp0"
start "" http://localhost:8080
where python >nul 2>nul && (python -m http.server 8080 & goto :eof)
where py >nul 2>nul && (py -m http.server 8080 & goto :eof)
where npx >nul 2>nul && (npx --yes serve -l 8080 . & goto :eof)
echo Weder Python noch Node gefunden. Bitte Python von https://python.org installieren.
pause
