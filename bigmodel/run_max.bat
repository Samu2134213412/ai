@echo off
rem Runs ollama_max.py with all arguments passed through.
cd /d "%~dp0"
python ollama_max.py %*
