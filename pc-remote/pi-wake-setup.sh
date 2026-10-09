#!/usr/bin/env bash
# Run on the always-on Raspberry Pi (in the same LAN as the PC):
#   sudo bash pi-wake-setup.sh AA:BB:CC:DD:EE:FF http://<pc-tailscale-name>.ts.net
# Installs the Wake-on-LAN relay as a service (starts at boot) and gives it a stable
# public HTTPS address via Tailscale Funnel. Open the printed link on the phone -> "PC anschalten".
set -euo pipefail
MAC="${1:?usage: sudo bash pi-wake-setup.sh AA:BB:CC:DD:EE:FF [pc-remote-url]}"
PC_URL="${2:-}"
DIR="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="${SUDO_USER:-pi}"

command -v python3 >/dev/null || apt-get install -y python3
command -v tailscale >/dev/null || curl -fsSL https://tailscale.com/install.sh | sh

cat >/etc/systemd/system/pc-remote-wake.service <<UNIT
[Unit]
Description=PC Remote wake relay
After=network-online.target
Wants=network-online.target

[Service]
User=${USER_NAME}
ExecStart=/usr/bin/python3 ${DIR}/wake.py --mac ${MAC} --pc-url "${PC_URL}"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now pc-remote-wake.service

tailscale status >/dev/null 2>&1 || tailscale up
tailscale funnel --bg 8766 || echo "Funnel muss ggf. im Tailscale-Adminbereich freigeschaltet werden (Link oben)."
sleep 2
TOKEN_FILE="$(getent passwd "$USER_NAME" | cut -d: -f6)/.pc-remote-wake-token"
DNS="$(tailscale status --json | python3 -c 'import sys,json;print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
echo
echo "Fertig. Am Handy oeffnen und als Lesezeichen speichern:"
echo "  https://${DNS}/#$(cat "$TOKEN_FILE")"
