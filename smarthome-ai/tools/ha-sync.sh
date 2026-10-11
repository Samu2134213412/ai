#!/usr/bin/env bash
# Holt den aktuellen Stand aus GitHub und kopiert homeassistant/ nach /config.
#
# Läuft auf dem Pi im Add-on „Advanced SSH & Web Terminal“.
# Einrichtung (Deploy-Key usw.): docs/setup/M1-pi-homeassistant.md, Schritt 9.
#
# Bewusst nur in eine Richtung (Repo → Pi) und ohne Löschen: In der Oberfläche
# angelegte Automationen, secrets.yaml und die HA-Datenbank bleiben unberührt.
set -euo pipefail

REPO_URL="${REPO_URL:-git@github.com:samu2134213412/smarthome-ai.git}"
BRANCH="${BRANCH:-main}"
REPO_DIR="${REPO_DIR:-/share/smarthome-ai}"
DEPLOY_KEY="${DEPLOY_KEY:-/share/.ssh/smarthome_deploy}"
CONFIG_DIR="${CONFIG_DIR:-/config}"

command -v rsync >/dev/null || {
  echo "rsync fehlt: im Add-on unter Konfiguration → packages den Eintrag rsync hinzufügen und Add-on neu starten." >&2
  exit 1
}

export GIT_SSH_COMMAND="ssh -i ${DEPLOY_KEY} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"

if [ ! -d "${REPO_DIR}/.git" ]; then
  echo "→ Erstes Klonen nach ${REPO_DIR}"
  git clone --depth 1 --branch "${BRANCH}" "${REPO_URL}" "${REPO_DIR}"
else
  echo "→ Aktualisiere ${REPO_DIR}"
  git -C "${REPO_DIR}" fetch --depth 1 origin "${BRANCH}"
  git -C "${REPO_DIR}" reset --hard "origin/${BRANCH}"
fi
echo "   Stand: $(git -C "${REPO_DIR}" log -1 --format='%h %s')"

echo "→ Kopiere homeassistant/ nach ${CONFIG_DIR}"
# secrets.yaml und von der Oberfläche verwaltete Dateien nie überschreiben,
# auch wenn sie versehentlich ins Repo geraten.
rsync -a --itemize-changes \
  --exclude 'secrets.yaml' \
  --exclude 'automations.yaml' \
  --exclude 'scripts.yaml' \
  --exclude 'scenes.yaml' \
  --exclude '.storage/' \
  --exclude 'home-assistant_v2.db*' \
  --exclude '*.example' \
  --exclude 'README.md' \
  "${REPO_DIR}/homeassistant/" "${CONFIG_DIR}/"

echo "→ Prüfe Konfiguration"
if ha core check; then
  echo "✔ Konfiguration gültig. Übernehmen mit:  ha core restart"
else
  echo "✘ Konfiguration fehlerhaft – NICHT neu starten. Fehler oben beheben." >&2
  exit 1
fi
