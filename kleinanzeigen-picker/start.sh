#!/usr/bin/env sh
cd "$(dirname "$0")" || exit 1
command -v node >/dev/null 2>&1 || { echo "Node.js fehlt: https://nodejs.org"; exit 1; }
exec node server.js --open
