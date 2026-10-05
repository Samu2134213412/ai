#!/usr/bin/env bash
# Tutor installieren (macOS/Linux): legt den Ordner "Tutor" und das Programm auf den Desktop.
#
#   Einzeiler:
#   curl -fsSL https://raw.githubusercontent.com/Samu2134213412/ai/ccr-b87b8acb-etedpt/tutor/install.sh | bash
#
# Linux -> Tutor.AppImage, macOS -> Tutor.dmg. Gibt es im GitHub-Release keine fertige Datei, wird
# sie selbst gebaut (braucht Node.js 20+). Umgebungsvariablen: TUTOR_REPO, TUTOR_BRANCH,
# TUTOR_DESKTOP_DIR (Zielordner statt Desktop), TUTOR_PREBUILT (fertige Datei nutzen).
set -euo pipefail

REPO="${TUTOR_REPO:-Samu2134213412/ai}"
BRANCH="${TUTOR_BRANCH:-ccr-b87b8acb-etedpt}"
say()  { printf '\033[36m>> %s\033[0m\n' "$*"; }
fail() { printf '\033[31mFEHLER: %s\033[0m\n' "$*" >&2; exit 1; }

case "$(uname -s)" in
  Darwin) EXE_NAME="Tutor.dmg";      SCRIPT="dist:mac" ;;
  Linux)  EXE_NAME="Tutor.AppImage"; SCRIPT="dist:linux" ;;
  *) fail "Dieses Skript ist für macOS/Linux. Unter Windows: install.ps1." ;;
esac

if [ -n "${TUTOR_DESKTOP_DIR:-}" ]; then DESKTOP="$TUTOR_DESKTOP_DIR"
elif command -v xdg-user-dir >/dev/null 2>&1 && [ -d "$(xdg-user-dir DESKTOP 2>/dev/null)" ]; then DESKTOP="$(xdg-user-dir DESKTOP)"
else DESKTOP="$HOME/Desktop"; fi
mkdir -p "$DESKTOP"
TARGET="$DESKTOP/Tutor"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# 1. Quellcode: lokaler Ordner (Skript liegt in tutor/) oder GitHub
SELF="${BASH_SOURCE[0]:-}"
SRC=""
if [ -n "$SELF" ] && [ -f "$(dirname "$SELF")/desktop/package.json" ]; then
  SRC="$(cd "$(dirname "$SELF")" && pwd)"
  say "Nutze lokalen Ordner: $SRC"
else
  say "Lade Tutor von GitHub ($REPO, $BRANCH) ..."
  curl -fsSL "https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz" | tar -xz -C "$WORK" \
    || fail "Download fehlgeschlagen (Branch '$BRANCH' vorhanden? Internet?)."
  SRC="$(find "$WORK" -mindepth 2 -maxdepth 2 -type d -name tutor | head -n1)"
  [ -f "$SRC/desktop/package.json" ] || fail "Im Download wurde kein Tutor-Ordner gefunden."
fi

# 2. Ordner auf den Desktop (vorhandene Daten bleiben, Build-Reste werden nicht kopiert)
mkdir -p "$TARGET"
if [ "$(cd "$SRC" && pwd -P)" != "$(cd "$TARGET" && pwd -P)" ]; then
  say "Kopiere nach $TARGET ..."
  (cd "$SRC" && tar --exclude=node_modules --exclude=dist --exclude=www --exclude=.git --exclude=__pycache__ -cf - .) \
    | (cd "$TARGET" && tar -xf -)
fi

# 3. Programm besorgen: fertige Datei, Release oder selbst bauen
EXE=""
if [ -n "${TUTOR_PREBUILT:-}" ] && [ -f "$TUTOR_PREBUILT" ]; then
  EXE="$TUTOR_PREBUILT"; say "Nutze fertige Datei: $EXE"
fi
if [ -z "$EXE" ]; then
  say "Suche fertige $EXE_NAME im GitHub-Release ..."
  URL="$(curl -fsSL "https://api.github.com/repos/$REPO/releases" 2>/dev/null \
        | grep -o "https://[^\"]*/tutor-desktop-v[^\"/]*/$EXE_NAME" | head -n1 || true)"
  if [ -n "$URL" ] && curl -fsSL "$URL" -o "$WORK/$EXE_NAME"; then EXE="$WORK/$EXE_NAME"; fi
fi
if [ -z "$EXE" ]; then
  say "Keine fertige Datei gefunden – baue $EXE_NAME selbst (dauert einige Minuten) ..."
  command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1 \
    || fail "Node.js 20+ fehlt (https://nodejs.org). Danach den Befehl wiederholen."
  export CSC_IDENTITY_AUTO_DISCOVERY=false   # ohne Signierzertifikat bauen
  (cd "$TARGET/desktop" && npm install --no-audit --no-fund && npm run "$SCRIPT") || fail "Bauen fehlgeschlagen."
  EXE="$TARGET/desktop/dist/$EXE_NAME"
  [ -f "$EXE" ] || fail "$EXE_NAME wurde nicht erzeugt."
fi

# 4. Programm auf den Desktop und in den Ordner
cp -f "$EXE" "$DESKTOP/$EXE_NAME"; cp -f "$EXE" "$TARGET/$EXE_NAME"
[ "$EXE_NAME" = "Tutor.AppImage" ] && chmod +x "$DESKTOP/$EXE_NAME" "$TARGET/$EXE_NAME"

printf '\n\033[32mFertig! Auf dem Desktop liegen jetzt:\033[0m\n  - %s   (Doppelklick/Start)\n  - Tutor/   (Ordner, Anleitung: Tutor/README.md)\n' "$EXE_NAME"
if ! command -v ollama >/dev/null 2>&1; then
  printf '\n\033[33mNoch nötig: Ollama (https://ollama.com/download), danach:\033[0m\n  ollama pull qwen2.5:32b   # kleiner Rechner: qwen2.5:7b\n  ollama pull qwen2.5vl:7b  # zum Lesen deiner Seiten\n'
fi
