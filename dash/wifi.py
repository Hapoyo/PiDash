"""Wi-Fi del Raspberry: salva nuove credenziali (SSID e password) con NetworkManager (`nmcli`).

`python -m dash --wifi` le chiede da terminale (SSID, poi la password nascosta, due volte) e
aggiorna il profilo di quella rete, o lo crea, e si collega. Serve quando la rete cambia o la
password non è più valida. La password sta solo nei parametri di `nmcli` (visibile per un attimo
a chi guarda i processi del Pi) e non finisce mai in un messaggio, in un log né in un file del
progetto: la conserva NetworkManager in `/etc/NetworkManager/system-connections` (permessi 600).

Il Pi 3 Model B vede solo il 2,4 GHz: se la rete compare solo a 5 GHz, o non compare, si avvisa.
"""
from __future__ import annotations

import os
import re
import subprocess
from typing import Callable

# (comando) → (codice di uscita, testo di uscita e di errore); si sostituisce nei test
Esegui = Callable[[list[str]], "tuple[int, str]"]

SSID_MAX_BYTE = 32
PASSWORD_MIN, PASSWORD_MAX = 8, 63        # WPA2/WPA3 personal: 8–63 caratteri, oppure 64 cifre esadecimali
GHZ5_MHZ = 5000
TIMEOUT_S = 60


class WifiError(RuntimeError):
    """Credenziali non valide o `nmcli` che non riesce: il testo è pronto per il terminale."""


def _esegui(cmd: list[str]) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S, check=False)
    except FileNotFoundError:
        raise WifiError(f"{cmd[0]} non trovato: serve NetworkManager (Raspberry Pi OS Bookworm o successivo)") from None
    except subprocess.TimeoutExpired:
        raise WifiError("nmcli non risponde") from None
    return r.returncode, (r.stdout + r.stderr).strip()


def valida(ssid: str, password: str) -> None:
    """Rifiuta credenziali che la rete non accetterebbe, prima di toccare qualcosa."""
    if not ssid.strip() or ssid != ssid.strip():
        raise WifiError("SSID vuoto o con spazi all'inizio o alla fine")
    if len(ssid.encode("utf-8")) > SSID_MAX_BYTE:
        raise WifiError(f"SSID troppo lungo (al massimo {SSID_MAX_BYTE} byte)")
    esadecimale = len(password) == 64 and re.fullmatch(r"[0-9a-fA-F]{64}", password)
    if not esadecimale and not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        raise WifiError(f"la password deve avere da {PASSWORD_MIN} a {PASSWORD_MAX} caratteri")
    if any(ord(c) < 32 or ord(c) == 127 for c in password):
        raise WifiError("la password contiene caratteri di controllo")


def _campi(riga: str) -> list[str]:
    """Una riga `nmcli -t`: campi separati da ":" (un ":" nel valore è scritto "\\:")."""
    return [c.replace("\\:", ":").replace("\\\\", "\\") for c in re.split(r"(?<!\\):", riga)]


def reti(esegui: Esegui = _esegui) -> list[tuple[str, int, int, str]]:
    """Reti visibili come (ssid, frequenza MHz, segnale, sicurezza), dalla più forte."""
    codice, testo = esegui(["nmcli", "-t", "-f", "SSID,FREQ,SIGNAL,SECURITY", "device", "wifi",
                            "list", "--rescan", "yes"])
    if codice != 0:
        raise WifiError(f"elenco delle reti non riuscito: {_riassunto(testo)}")
    trovate: list[tuple[str, int, int, str]] = []
    for riga in testo.splitlines():
        c = _campi(riga)
        if len(c) >= 4 and c[0]:
            try:
                trovate.append((c[0], int(c[1].split()[0]), int(c[2]), c[3]))
            except (ValueError, IndexError):
                continue
    return sorted(trovate, key=lambda r: -r[2])


def avvisi(ssid: str, elenco: list[tuple[str, int, int, str]]) -> list[str]:
    """Cosa non va con la rete scelta, se si vede: manca, o solo a 5 GHz."""
    mie = [r for r in elenco if r[0] == ssid]
    if not mie:
        return [f"la rete «{ssid}» non si vede ora: controlla il nome (maiuscole comprese) e che il "
                "router sia acceso; si salva lo stesso, e il Pi si collegherà quando comparirà"]
    if all(r[1] >= GHZ5_MHZ for r in mie):
        return [f"la rete «{ssid}» è solo a 5 GHz: il Raspberry Pi 3 non può collegarsi, serve il "
                "2,4 GHz (di solito è un'altra rete, o si attiva sul router)"]
    return []


def _riassunto(testo: str) -> str:
    """L'ultima riga dell'errore di nmcli, senza il prefisso "Error: "."""
    righe = [r for r in testo.splitlines() if r.strip()]
    return re.sub(r"^Error:\s*", "", righe[-1]) if righe else "nessun dettaglio"


def _dispositivo(esegui: Esegui) -> str:
    """Il nome dell'interfaccia Wi-Fi (di solito wlan0)."""
    codice, testo = esegui(["nmcli", "-t", "-f", "DEVICE,TYPE", "device"])
    if codice == 0:
        for riga in testo.splitlines():
            c = _campi(riga)
            if len(c) >= 2 and c[1] == "wifi":
                return c[0]
    raise WifiError("nessuna interfaccia Wi-Fi trovata (il Pi 3 Model B ha il Wi-Fi integrato: "
                    "controlla `nmcli device`)")


def _profilo_esiste(ssid: str, esegui: Esegui) -> bool:
    codice, testo = esegui(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"])
    if codice != 0:
        raise WifiError(f"elenco dei profili non riuscito: {_riassunto(testo)}")
    return any(_campi(r)[:1] == [ssid] and _campi(r)[1:2] == ["802-11-wireless"]
               for r in testo.splitlines())


def aggiorna(ssid: str, password: str, esegui: Esegui = _esegui, root: bool | None = None) -> str:
    """Salva SSID e password (aggiorna il profilo o ne crea uno) e si collega; torna l'indirizzo IP.

    `root`: vero se si è già root; altrimenti i comandi che cambiano le connessioni vanno con `sudo`.
    Se il collegamento fallisce il profilo resta salvato con le nuove credenziali (WifiError lo dice).
    """
    valida(ssid, password)
    sudo = [] if (os.geteuid() == 0 if root is None else root) else ["sudo"]
    dispositivo = _dispositivo(esegui)
    esiste = _profilo_esiste(ssid, esegui)
    comune = ["wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", password, "connection.autoconnect", "yes"]
    if esiste:
        cmd = sudo + ["nmcli", "connection", "modify", "id", ssid, "802-11-wireless.ssid", ssid, *comune]
    else:
        cmd = sudo + ["nmcli", "connection", "add", "type", "wifi", "ifname", dispositivo,
                      "con-name", ssid, "ssid", ssid, *comune]
    codice, testo = esegui(cmd)
    if codice != 0:
        raise WifiError(f"profilo non salvato: {_riassunto(testo).replace(password, '***')}")
    codice, testo = esegui(sudo + ["nmcli", "connection", "up", "id", ssid])
    if codice != 0:
        raise WifiError("credenziali salvate ma collegamento non riuscito: "
                        f"{_riassunto(testo).replace(password, '***')} "
                        "(password sbagliata, rete fuori portata o solo a 5 GHz?)")
    codice, testo = esegui(["nmcli", "-g", "IP4.ADDRESS", "device", "show", dispositivo])
    return testo.splitlines()[0].split("/")[0] if codice == 0 and testo.strip() else ""
