#!/bin/sh
# Startet den PC Baukasten auf http://localhost:8080
cd "$(dirname "$0")"
(sleep 1; xdg-open http://localhost:8080 2>/dev/null || open http://localhost:8080) &
exec python3 -m http.server 8080
