#!/usr/bin/env bash
# Toglie la console di testo dallo schermo del dashboard: niente login, messaggi di avvio o cursore
# lampeggiante (il "-" sul bordo sinistro). Da fare una volta sul Pi, poi riavviare.
# Uso: scripts/console-silenziosa.sh   (chiede la password di sudo)
set -euo pipefail

CMDLINE=/boot/firmware/cmdline.txt
[[ -f "$CMDLINE" ]] || CMDLINE=/boot/cmdline.txt
[[ -f "$CMDLINE" ]] || { echo "errore: cmdline.txt non trovato in /boot/firmware né in /boot" >&2; exit 1; }

# 1. cmdline.txt (una sola riga): console del kernel su tty3 invece di tty1, cursore spento di serie,
#    nessun logo e nessun messaggio sul tty1; copia di sicurezza accanto al file.
riga="$(tr -d '\n' < "$CMDLINE")"
nuova="$(sed -E 's/(^| )console=tty1( |$)/\1console=tty3\2/g' <<< "$riga")"
for opz in vt.global_cursor_default=0 consoleblank=0 loglevel=3 logo.nologo; do
    grep -qE "(^| )${opz%%=*}(=| |\$)" <<< "$nuova" || nuova="$nuova $opz"
done
if [[ "$nuova" != "$riga" ]]; then
    sudo cp -n "$CMDLINE" "$CMDLINE.pi-dash.bak"
    echo "$nuova" | sudo tee "$CMDLINE" >/dev/null
    echo "aggiornato $CMDLINE (copia: $CMDLINE.pi-dash.bak)"
else
    echo "$CMDLINE già a posto"
fi

# 2. nessun login sul tty1 (il prompt riaccende il cursore e scrive sopra il dashboard)
sudo systemctl disable --now getty@tty1.service 2>/dev/null || true
sudo systemctl mask getty@tty1.service
echo "login sul tty1 disattivato"

echo "fatto: riavvia con 'sudo reboot'"
