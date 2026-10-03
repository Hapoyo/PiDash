"""Philips Hue: accende, spegne e regola le luci del bridge in rete locale.

API v1 del bridge su HTTPS (la v2 è per le nuove funzioni, qui bastano stanze e luminosità).
Il bridge ha un certificato autofirmato: non si verifica, perché il traffico resta nella rete
di casa e l'indirizzo è quello scritto in configurazione; la chiave non compare mai nei log né
nei messaggi. Le chiamate sono sincrone con un timeout corto (`hue.timeout_s`, 2 s): un bridge
spento rallenta il dashboard di quel tempo, non lo blocca.
"""
from __future__ import annotations

import json
import logging
import re
import ssl
import threading
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable
from urllib import error, request

log = logging.getLogger(__name__)

CACHE_S = 300.0          # le stanze cambiano di rado: si rileggono ogni 5 minuti
RICERCA_S = 60.0         # pausa tra due ricerche del bridge: un bridge spento non rallenta ogni comando
LINK_TIMEOUT_S = 30.0    # tempo per premere il tasto del bridge durante la registrazione
# Parole che il modello può lasciare nel nome della stanza ("la luce del soggiorno").
ARTICOLI = frozenset({"il", "lo", "la", "l", "le", "i", "gli", "di", "del", "della", "dello", "dei",
                      "delle", "in", "nel", "nella", "al", "alla", "luce", "luci", "stanza"})
TUTTE = frozenset({"", "tutte", "tutto", "tutti", "all", "casa", "ovunque"})

# Colori (tinta 0–65535, saturazione 0–254) e temperature (ct in mired: 153 fredda … 500 calda)
# dell'API v1; le parole italiane che li nominano stanno in `frasi.py` e in `needle.azioni`.
COLORI: dict[str, tuple[int, int]] = {
    "rosso": (0, 254), "arancione": (6000, 254), "giallo": (12750, 254), "verde": (25500, 254),
    "azzurro": (36000, 200), "blu": (46920, 254), "viola": (50000, 254), "rosa": (56100, 140),
}
TEMPERATURE: dict[str, int] = {"fredda": 200, "bianca": 250, "naturale": 300, "calda": 400}

Send = Callable[[str, str, "dict[str, Any] | None"], Any]  # (metodo, percorso, corpo) → JSON[str, str, "dict[str, Any] | None"], Any]  # (metodo, percorso, corpo) → JSON


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
                 clock: Callable[[], float] = time.monotonic,
                 ritrova: Callable[[], str] | None = None,
                 fabbrica: Callable[[str, str, float], Send] = http_send,
                 on_trovato: Callable[[str], None] | None = None) -> None:
        """`ritrova` dà l'indirizzo attuale del bridge quando quello salvato non risponde (di norma
        `scopri`; senza `send` di prova è attivo da solo); `on_trovato` salva il nuovo indirizzo."""
        self.bridge = str(cfg.get("bridge") or "")
        self.key = str(cfg.get("key") or "")
        self._timeout = max(0.5, float(cfg.get("timeout_s", 2)))
        self._fabbrica = fabbrica
        self._send = send or fabbrica(self.bridge, self.key, self._timeout)
        self._ritrova = ritrova if ritrova is not None or send is not None else scopri
        self._on_trovato = on_trovato
        self._cercato = -RICERCA_S * 2
        self._clock = clock
        self._lock = threading.Lock()
        self._stanze: list[Stanza] = []
        self._letto = -CACHE_S * 2

    @property
    def configurato(self) -> bool:
        return bool(self.bridge and self.key)

    # --- indirizzo -------------------------------------------------------
    def _chiama(self, metodo: str, percorso: str, corpo: dict[str, Any] | None) -> Any:
        """Una chiamata al bridge; se non risponde ne cerca il nuovo indirizzo (l'IP può cambiare)."""
        try:
            return self._send(metodo, percorso, corpo)
        except HueError:
            if not self._cerca_bridge():
                raise
        return self._send(metodo, percorso, corpo)

    def _cerca_bridge(self) -> bool:
        """Ritrova il bridge dopo un silenzio; True se l'indirizzo è cambiato e la chiave vale ancora."""
        if self._ritrova is None or not self.configurato:
            return False
        with self._lock:
            if self._clock() - self._cercato < RICERCA_S:
                return False
            self._cercato = self._clock()
        try:
            nuovo = self._ritrova()
            if not nuovo or nuovo == self.bridge:
                return False
            prova = self._fabbrica(nuovo, self.key, self._timeout)
            if not isinstance(prova("GET", "lights", None), dict):   # altra chiave: non è il nostro bridge
                return False
        except HueError:
            return False
        self.bridge, self._send = nuovo, prova
        log.info("bridge hue ritrovato a un nuovo indirizzo: %s", nuovo)
        if self._on_trovato is not None:
            self._on_trovato(nuovo)
        return True

    # --- stanze ----------------------------------------------------------
    def stanze(self, forza: bool = False) -> list[Stanza]:
        """Stanze del bridge con quante luci sono raggiungibili (in cache per 5 minuti)."""
        with self._lock:
            if not forza and self._clock() - self._letto < CACHE_S:
                return self._stanze
        luci, gruppi = self._chiama("GET", "lights", None), self._chiama("GET", "groups", None)
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
    def imposta(self, stanza: Stanza | None, acceso: bool, percentuale: int | None = None,
                colore: str | None = None, temperatura: str | None = None,
                delta: int | None = None) -> None:
        """Accende o spegne una stanza (None = tutte le luci), con luminosità 1–100 % se data.

        `colore` e `temperatura` sono chiavi di `COLORI` e `TEMPERATURE`; `delta` (−100…100) alza
        o abbassa la luminosità di quei punti percentuali rispetto a com'è ora.
        """
        corpo: dict[str, Any] = {"on": acceso}
        if percentuale is not None:
            corpo["bri"] = max(1, min(254, round(percentuale * 254 / 100)))
        elif delta:
            corpo["bri_inc"] = max(-254, min(254, round(delta * 254 / 100)))
        if colore is not None:
            corpo["hue"], corpo["sat"] = COLORI[colore]
        elif temperatura is not None:
            corpo["ct"] = TEMPERATURE[temperatura]
        risposta = self._chiama("PUT", f"groups/{'0' if stanza is None else stanza.id}/action", corpo)
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
