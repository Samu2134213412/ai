@echo off
REM CodePilot Remote - one-time setup on Windows.
REM Installs dependencies, sets Ollama's context window, and diagnoses the
REM whole chain. It never downloads a model without asking first.
setlocal EnableDelayedExpansion

cd /d "%~dp0"
echo.
echo  CodePilot Remote - setup
echo  ========================
echo.

REM ---------------------------------------------------------------- python ---
where python >nul 2>&1
if errorlevel 1 (
  echo  [X] Python was not found on PATH.
  echo      Install Python 3.10+ from https://www.python.org/downloads/
  echo      and tick "Add python.exe to PATH" during installation.
  goto :stop
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  [ok] Python !PYVER!

REM ------------------------------------------------------------------ node ---
where node >nul 2>&1
if errorlevel 1 (
  echo  [!] Node.js was not found. You need it only for the phone app.
  echo      Get it from https://nodejs.org/ when you want to run mobile\.
) else (
  for /f %%v in ('node --version') do echo  [ok] Node.js %%v
)

REM ------------------------------------------------------------- claude code --
where claude >nul 2>&1
if errorlevel 1 (
  echo  [X] Claude Code was not found on PATH.
  echo      Install it with:  npm install -g @anthropic-ai/claude-code
  goto :stop
)
echo  [ok] Claude Code

REM ---------------------------------------------------------------- ollama ---
where ollama >nul 2>&1
if errorlevel 1 (
  echo  [X] Ollama was not found on PATH.
  echo      Install it from https://ollama.com/download  ^(version 0.14.0 or newer^)
  goto :stop
)
for /f "tokens=*" %%v in ('ollama --version 2^>^&1') do echo  [ok] %%v

echo.
echo  --- Ollama context window ---
echo  Ollama sets its context window on the SERVER process, not per request.
echo  CodePilot defaults to 32768 tokens, which is the safe size for a 30B
echo  model on a 24 GB card.
echo.
if "%OLLAMA_CONTEXT_LENGTH%"=="32768" (
  echo  [ok] OLLAMA_CONTEXT_LENGTH is already 32768 in this session.
) else (
  echo  Current value in this session: "%OLLAMA_CONTEXT_LENGTH%"
  set /p CTXOK="  Set OLLAMA_CONTEXT_LENGTH=32768 permanently for your user? [Y/n] "
  if /i not "!CTXOK!"=="n" (
    setx OLLAMA_CONTEXT_LENGTH 32768 >nul
    echo  [ok] Set. You MUST now quit Ollama from the system tray and reopen it,
    echo       otherwise the old, smaller window stays in effect.
  ) else (
    echo  [!] Skipped. If sessions behave oddly, this is the usual reason.
  )
)

REM ------------------------------------------------------------------ model ---
echo.
echo  --- Model ---
ollama list 2>nul | findstr /i "qwen3-coder" >nul
if errorlevel 1 (
  echo  [!] No qwen3-coder model is installed.
  echo      qwen3-coder:30b is roughly 18 GB. CodePilot will never pull it
  echo      behind your back.
  set /p PULLOK="  Pull qwen3-coder:30b now? [y/N] "
  if /i "!PULLOK!"=="y" (
    ollama pull qwen3-coder:30b
  ) else (
    echo  [!] Skipped. Run this yourself later:  ollama pull qwen3-coder:30b
  )
) else (
  echo  [ok] A qwen3-coder model is installed:
  ollama list | findstr /i "qwen3-coder"
)

REM ------------------------------------------------------------ dependencies --
echo.
echo  --- Python dependencies ---
if not exist "%~dp0server\.venv" (
  echo  Creating server\.venv ...
  python -m venv "%~dp0server\.venv" || goto :stop
)
"%~dp0server\.venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
"%~dp0server\.venv\Scripts\python.exe" -m pip install -r "%~dp0server\requirements.txt" || goto :stop
echo  [ok] Dependencies installed.

REM --------------------------------------------------------------- bind mode --
echo.
echo  --- Network ---
echo  By default CodePilot listens on 127.0.0.1 only, so your phone cannot
echo  reach it. "private" listens on the LAN and on Tailscale - still never
echo  on the public internet.
set /p LANOK="  Allow your phone to connect? [Y/n] "
cd /d "%~dp0server"
if /i not "%LANOK%"=="n" (
  "%~dp0server\.venv\Scripts\python.exe" -m codepilot --set bind_mode=private --check >nul 2>&1
  echo  [ok] Network access set to private.
)

REM ------------------------------------------------------------------ doctor --
echo.
echo  --- Diagnosis ---
echo  Walking the whole chain, from Claude Code to your phone.
echo.
"%~dp0server\.venv\Scripts\python.exe" -m codepilot --doctor

echo.
echo  ========================================================
echo   Setup finished. To start CodePilot:   start.bat
echo   Then open  http://127.0.0.1:8765/  and pair your phone.
echo  ========================================================
pause
exit /b 0

:stop
echo.
echo  Setup stopped. Fix the item marked [X] above and run setup.bat again.
pause
exit /b 1
