#!/usr/bin/env bash
# Aggiorna pi-dash dal repository GitHub e riavvia il servizio.
# Uso: scripts/aggiorna.sh [--no-test]
# Passi: controlla modifiche locali → git pull → dipendenze → test e configurazione →
# servizio (se il file è cambiato) → riavvio. Se i controlli falliscono torna alla versione di prima.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
    || { echo "errore: $DIR non viene da GitHub (installazione da zip): vedi docs/installazione.md § 7.1" >&2; exit 1; }
PY="$DIR/.venv/bin/python"
[[ -x "$PY" ]] || PY=python3
TEST=1
[[ "${1:-}" == "--no-test" ]] && TEST=0

info() { echo "· $*"; }
fail() { echo "errore: $*" >&2; exit 1; }

# 1. Modifiche locali ai file in Git: le due note si sistemano da sole, il resto blocca.
if ! git diff --quiet -- systemd/pi-dash.service; then
    # vecchia installazione con "sed -i": la copia attiva sta in /etc, qui si ripristina
    info "ripristino systemd/pi-dash.service (la copia installata non cambia)"
    git checkout -- systemd/pi-dash.service
fi
if ! git diff --quiet -- config.json; then
    [[ -e config.local.json ]] && fail "config.json è modificato e config.local.json esiste già:
  sposta le tue modifiche in config.local.json, poi: git checkout -- config.json"
    info "sposto le tue impostazioni da config.json a config.local.json"
    cp config.json config.local.json
    git checkout -- config.json
fi
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    git status --short --untracked-files=no
    fail "ci sono file modificati a mano (elenco sopra): salvali altrove o annulla con git checkout -- <file>"
fi

# 2. Scarica e applica
info "controllo aggiornamenti su $(git remote get-url origin) ($(git rev-parse --abbrev-ref HEAD))"
git fetch --quiet origin || fail "GitHub non raggiungibile: controlla la rete"
OLD="$(git rev-parse HEAD)"
NEW="$(git rev-parse '@{u}')"
if [[ "$OLD" == "$NEW" ]]; then
    info "già all'ultima versione ($(git log -1 --format='%h %s'))"
    exit 0
fi
git merge --ff-only --quiet '@{u}' \
    || fail "la versione locale ha commit propri: aggiornamento automatico impossibile"
echo "novità:"
git log --format='  %h %s' "$OLD..HEAD"

rollback() {
    echo "errore: $1 — torno alla versione precedente" >&2
    git reset --quiet --hard "$OLD"
    exit 1
}

# 3. Dipendenze e controlli
if git diff --quiet "$OLD" HEAD -- requirements.txt; then :; else
    info "aggiorno le dipendenze"
    "$PY" -m pip install --quiet -r requirements.txt || rollback "installazione dipendenze fallita"
fi
if (( TEST )); then
    info "eseguo i test"
    LOG="$(mktemp)"
    "$PY" -m unittest -q 2>"$LOG" || { tail -20 "$LOG" >&2; rm -f "$LOG"; rollback "test falliti"; }
    rm -f "$LOG"
fi
"$PY" -c "from dash.config import load_config; from dash.widgets import WIDGET_NAMES; \
load_config('config.json', WIDGET_NAMES)" || rollback "configurazione non valida con la nuova versione"

# 4. Servizio
if systemctl cat pi-dash >/dev/null 2>&1; then
    if ! git diff --quiet "$OLD" HEAD -- systemd/pi-dash.service; then
        info "il file del servizio è cambiato: lo reinstallo"
        "$DIR/scripts/installa-servizio.sh"
    fi
    info "riavvio pi-dash"
    sudo systemctl restart pi-dash
    sleep 3
    systemctl is-active --quiet pi-dash \
        || fail "pi-dash non è partito: sudo journalctl -u pi-dash -n 50"
else
    info "servizio non installato: avvio automatico con scripts/installa-servizio.sh"
fi
# 5. Needle, se installato: il file del servizio si reinstalla a mano (serve la cartella del modello),
# le funzioni nuove basta ricaricarle
if systemctl cat needle >/dev/null 2>&1; then
    if ! git diff --quiet "$OLD" HEAD -- systemd/needle.service; then
        info "il file del servizio needle è cambiato: rilancia scripts/installa-needle.sh"
    elif ! git diff --quiet "$OLD" HEAD -- needle/tools.json; then
        info "le funzioni di needle sono cambiate: riavvio needle"
        sudo systemctl restart needle
    fi
fi
info "aggiornato a $(git log -1 --format='%h %s') · versione $("$PY" -m dash --version | cut -d' ' -f2)"
