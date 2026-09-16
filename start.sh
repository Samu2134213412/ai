#!/usr/bin/env bash
# CodePilot Remote - start the desktop server (API + web dashboard) on macOS/Linux.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
venv="$here/server/.venv"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[CodePilot] python3 was not found on PATH. Install Python 3.10 or newer." >&2
  exit 1
fi

if [ ! -d "$venv" ]; then
  echo "[CodePilot] Creating a virtual environment in server/.venv ..."
  python3 -m venv "$venv"
  "$venv/bin/python" -m pip install --upgrade pip >/dev/null
  echo "[CodePilot] Installing dependencies ..."
  "$venv/bin/python" -m pip install -r "$here/server/requirements.txt"
fi

cd "$here/server"
exec "$venv/bin/python" -m codepilot "$@"
