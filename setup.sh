#!/usr/bin/env bash
# CodePilot Remote - one-time setup on macOS/Linux. Mirrors setup.bat.
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
venv="$here/server/.venv"
ctx=32768

say() { printf '  %s\n' "$*"; }
stop() { echo; say "Setup stopped. Fix the item marked [X] above and run setup.sh again."; exit 1; }

echo
echo " CodePilot Remote - setup"
echo " ========================"
echo

command -v python3 >/dev/null || { say "[X] python3 not found. Install Python 3.10+."; stop; }
say "[ok] $(python3 --version)"
command -v node >/dev/null && say "[ok] Node.js $(node --version)" \
  || say "[!] Node.js not found - needed only for the phone app."
command -v claude >/dev/null || { say "[X] Claude Code not found. npm install -g @anthropic-ai/claude-code"; stop; }
say "[ok] Claude Code $(claude --version 2>/dev/null | head -1)"
command -v ollama >/dev/null || { say "[X] Ollama not found. https://ollama.com/download (0.14.0+)"; stop; }
say "[ok] $(ollama --version 2>&1 | head -1)"

echo
say "--- Ollama context window ---"
if [ "${OLLAMA_CONTEXT_LENGTH:-}" = "$ctx" ]; then
  say "[ok] OLLAMA_CONTEXT_LENGTH is already $ctx in this shell."
else
  say "Ollama sets its window on the server process, not per request."
  say "Add this to your shell profile, then restart Ollama:"
  say "    export OLLAMA_CONTEXT_LENGTH=$ctx"
fi

echo
say "--- Model ---"
if ollama list 2>/dev/null | grep -qi qwen3-coder; then
  say "[ok] A qwen3-coder model is installed:"
  ollama list | grep -i qwen3-coder | sed 's/^/      /'
else
  say "[!] No qwen3-coder model installed. qwen3-coder:30b is roughly 18 GB."
  read -r -p "  Pull qwen3-coder:30b now? [y/N] " reply
  if [ "${reply:-n}" = "y" ] || [ "${reply:-n}" = "Y" ]; then
    ollama pull qwen3-coder:30b
  else
    say "[!] Skipped. Run it yourself later: ollama pull qwen3-coder:30b"
  fi
fi

echo
say "--- Python dependencies ---"
[ -d "$venv" ] || python3 -m venv "$venv" || stop
"$venv/bin/python" -m pip install --upgrade pip >/dev/null 2>&1
"$venv/bin/python" -m pip install -r "$here/server/requirements.txt" >/dev/null || stop
say "[ok] Dependencies installed."

echo
say "--- Network ---"
say "Default is 127.0.0.1 only, so a phone cannot connect."
read -r -p "  Allow your phone to connect (LAN + Tailscale)? [Y/n] " reply
cd "$here/server"
if [ "${reply:-y}" != "n" ] && [ "${reply:-y}" != "N" ]; then
  "$venv/bin/python" -m codepilot --set bind_mode=private --check >/dev/null 2>&1
  say "[ok] Network access set to private."
fi

echo
say "--- Diagnosis ---"
echo
"$venv/bin/python" -m codepilot --doctor

echo
echo " ========================================================"
echo "  Setup finished. To start CodePilot:   ./start.sh"
echo "  Then open http://127.0.0.1:8765/ and pair your phone."
echo " ========================================================"
