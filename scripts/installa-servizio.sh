#!/usr/bin/env bash
# Installa o aggiorna il servizio systemd pi-dash per l'utente e la cartella correnti.
# Uso: scripts/installa-servizio.sh   (chiede la password di sudo)
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UTENTE="$(id -un)"
DEST=/etc/systemd/system/pi-dash.service

if [[ "$UTENTE" == root ]]; then
    echo "errore: lancialo come utente normale, non con sudo" >&2
    exit 1
fi

# Nel file del repository utente "pi" e cartella /home/pi/pi-dash: si sostituiscono
# solo quelle due voci, il file in Git resta intatto (git pull non trova conflitti).
sed -e "s|^User=pi$|User=${UTENTE}|" -e "s|/home/pi/pi-dash|${DIR}|g" \
    "$DIR/systemd/pi-dash.service" | sudo tee "$DEST" >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable pi-dash >/dev/null 2>&1
echo "servizio installato: $DEST (utente $UTENTE, cartella $DIR)"
