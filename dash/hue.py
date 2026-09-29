"""Philips Hue: accende, spegne e regola le luci del bridge in rete locale.

API v1 del bridge su HTTPS (la v2 è per le nuove funzioni, qui bastano stanze e luminosità).
Il bridge ha un certificato autofirmato: non si verifica, perché il traffico resta nella rete
di casa e l'indirizzo è quello scritto in configurazione; la chiave non compare mai nei log né
nei messaggi. Le chiamate sono sincrone con un timeout corto (`hue.timeout_s`, 2 s): un bridge
spento rallenta il dashboard di quel tempo, non lo blocca.
"""
from __future__ import annotations

import json
import re
import ssl
import threading
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable
from urllib import error, request

CACHE_S = 300.0          # le stanze cambiano di rado: si rileggono ogni 5 minuti
LINK_TIMEOUT_S = 30.0    # tempo per premere il tasto del bridge durante la registrazione
# Parole che il modello può lasciare nel nome della stanza ("la luce del soggiorno").
ARTICOLI = frozenset({"il", "lo", "la", "l", "le", "i", "gli", "di", "del", "della", "dello", "dei",
                      "delle", "in", "nel", "nella", "al", "alla", "luce", "luci", "stanza"})
TUTTE = frozenset({"", "tutte", "tutto", "tutti", "all", "casa", "ovunque"})

Send = Callable[[str, str, "dict[str, Any] | None"], Any]  # (metodo, percorso, corpo) → JSON


class HueError(RuntimeError):
    """Bridge irraggiungibile, chiave rifiutata o stanza non riconosciuta (testo per lo schermo)."""


@dataclass(frozen=True)
class Stanza:
    id: str
    nome: str
    luci: int
    raggiungibili: int


def _contesto() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # certificato autofirmato del bridge, rete locale
    return ctx


def _parole(testo: str) -> list[str]:
    """Parole minuscole senza accenti né articoli: "La luce del Soppalco" → ["soppalco"]."""
    base = unicodedata.normalize("NFKD", testo).encode("ascii", "ignore").decode("ascii").lower()
    return [p for p in re.findall(r"[a-z0-9]+", base) if p not in ARTICOLI]


def http_send(bridge: str, key: str, timeout_s: float) -> Send:
    """Invio vero al bridge; la chiave sta solo nell'URL e non finisce mai negli errori."""
    ctx = _contesto()

    def send(metodo: str, percorso: str, corpo: dict[str, Any] | None) -> Any:
        prefisso = f"https://{bridge}/api" + (f"/{key}" if key else "")
        req = request.Request(f"{prefisso}/{percorso}".rstrip("/"),
                              data=None if corpo is None else json.dumps(corpo).encode("utf-8"),
                              method=metodo)
        try:
            with request.urlopen(req, timeout=timeout_s, context=ctx) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))
        except (error.URLError, OSError, ValueError):
            raise HueError("bridge non risponde") from None   # niente URL (c'è la chiave) nel testo
    return send


class Hue:
    """Stanze e comandi del bridge; `send` si sostituisce nei test."""

    def __init__(self, cfg: dict[str, Any], send: Send | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.bridge = str(cfg.get("bridge") or "")
        self.key = str(cfg.get("key") or "")
        self._send = send or http_send(self.bridge, self.key, max(0.5, float(cfg.get("timeout_s", 2))))
        self._clock = clock
        self._lock = threading.Lock()
        self._stanze: list[Stanza] = []
        self._letto = -CACHE_S * 2

    @property
    def configurato(self) -> bool:
        return bool(self.bridge and self.key)

    # --- stanze ----------------------------------------------------------
    def stanze(self, forza: bool = False) -> list[Stanza]:
        """Stanze del bridge con quante luci sono raggiungibili (in cache per 5 minuti)."""
        with self._lock:
            if not forza and self._clock() - self._letto < CACHE_S:
                return self._stanze
        luci, gruppi = self._send("GET", "lights", None), self._send("GET", "groups", None)
        if not isinstance(luci, dict) or not isinstance(gruppi, dict):
            raise HueError("chiave rifiutata dal bridge")  # il bridge risponde con una lista di errori
        stanze = [Stanza(gid, str(g.get("name", gid)), len(g.get("lights") or []),
                         sum(1 for lid in g.get("lights") or []
                             if (luci.get(lid) or {}).get("state", {}).get("reachable")))
                  for gid, g in gruppi.items() if g.get("type") == "Room"]
        with self._lock:
            self._stanze, self._letto = stanze, self._clock()
        return stanze

    def trova(self, nome: str) -> Stanza | None:
        """La stanza detta a voce; None per "tutte le luci". Ambigua o sconosciuta: HueError."""
        parole = _parole(nome)
        if not parole or " ".join(parole) in TUTTE:
            return None
        for forza in (False, True):   # una stanza appena creata compare alla seconda lettura
            stanze = self.stanze(forza)
            esatte = [s for s in stanze if _parole(s.nome) == parole]
            if len(esatte) == 1:
                return esatte[0]
            parziali = [s for s in stanze if set(parole) <= set(_parole(s.nome))
                        or set(_parole(s.nome)) <= set(parole)]
            if len(parziali) == 1 and not esatte:
                return parziali[0]
            if len(parziali) > 1 or len(esatte) > 1:
                raise HueError("stanza ambigua: " + ", ".join(s.nome for s in (esatte or parziali)))
        raise HueError(f"stanza sconosciuta: {nome.strip()}")

    # --- comandi ---------------------------------------------------------
    def imposta(self, stanza: Stanza | None, acceso: bool, percentuale: int | None = None) -> None:
        """Accende o spegne una stanza (None = tutte le luci), con luminosità 1–100 % se data."""
        corpo: dict[str, Any] = {"on": acceso}
        if percentuale is not None:
            corpo["bri"] = max(1, min(254, round(percentuale * 254 / 100)))
        risposta = self._send("PUT", f"groups/{'0' if stanza is None else stanza.id}/action", corpo)
        errori = [r["error"].get("description", "errore") for r in risposta
                  if isinstance(r, dict) and isinstance(r.get("error"), dict)] \
            if isinstance(risposta, list) else []
        if errori:
            raise HueError(f"bridge: {errori[0]}")


def scopri(timeout_s: float = 8.0) -> str:
    """Indirizzo del bridge dal servizio di Signify (discovery.meethue.com); serve la rete."""
    try:
        with request.urlopen("https://discovery.meethue.com", timeout=timeout_s) as resp:  # noqa: S310
            trovati = json.loads(resp.read().decode("utf-8"))
        return str(trovati[0]["internalipaddress"])
    except (error.URLError, OSError, ValueError, IndexError, KeyError, TypeError):
        raise HueError("bridge non trovato: passa l'indirizzo, --hue-registra 192.168.x.y") from None


def registra(bridge: str, send: Send | None = None, attesa_s: float = LINK_TIMEOUT_S,
             clock: Callable[[], float] = time.monotonic,
             pausa: Callable[[float], None] = time.sleep) -> str:
    """Chiede al bridge una chiave per PiDash: il tasto del bridge va premuto entro `attesa_s`."""
    invia = send or http_send(bridge, "", 5.0)
    fine = clock() + attesa_s
    while True:
        risposta = invia("POST", "", {"devicetype": "pidash#raspberry"})
        voce = risposta[0] if isinstance(risposta, list) and risposta else {}
        if isinstance(voce, dict) and isinstance(voce.get("success"), dict):
            return str(voce["success"]["username"])
        descrizione = (voce.get("error") or {}).get("description", "") if isinstance(voce, dict) else ""
        if "link button" not in descrizione or clock() >= fine:
            raise HueError(descrizione or "registrazione rifiutata (tasto del bridge non premuto?)")
        pausa(2.0)
