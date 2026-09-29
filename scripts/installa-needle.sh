#!/usr/bin/env bash
# Installa o aggiorna il servizio systemd needle per l'utente e le cartelle correnti.
# Uso: scripts/installa-needle.sh [CARTELLA_NEEDLE]   (chiede la password di sudo)
# CARTELLA_NEEDLE contiene `needle` e `needle3.cact` (default ~/needle): la crea
# `needle download linux-arm64 --out ~/needle`.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UTENTE="$(id -un)"
NEEDLE_DIR="$(cd "${1:-$HOME/needle}" 2>/dev/null && pwd)" || {
    echo "errore: cartella di needle non trovata: ${1:-$HOME/needle}" >&2
    echo "scaricala con: needle download linux-arm64 --out ~/needle" >&2
    exit 1
}
DEST=/etc/systemd/system/needle.service

if [[ "$UTENTE" == root ]]; then
    echo "errore: lancialo come utente normale, non con sudo" >&2
    exit 1
fi
for f in needle needle3.cact; do
    [[ -e "$NEEDLE_DIR/$f" ]] || { echo "errore: manca $NEEDLE_DIR/$f" >&2; exit 1; }
done
[[ -x "$NEEDLE_DIR/needle" ]] || chmod +x "$NEEDLE_DIR/needle"

# Nel file del repository utente "pi", /home/pi/needle e /home/pi/pi-dash: si sostituiscono
# solo quelle voci, il file in Git resta intatto (git pull non trova conflitti).
sed -e "s|^User=pi$|User=${UTENTE}|" -e "s|/home/pi/needle|${NEEDLE_DIR}|g" \
    -e "s|/home/pi/pi-dash|${DIR}|g" "$DIR/systemd/needle.service" | sudo tee "$DEST" >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable needle >/dev/null 2>&1
sudo systemctl restart needle
echo "servizio installato e avviato: $DEST (utente $UTENTE, needle in $NEEDLE_DIR)"
