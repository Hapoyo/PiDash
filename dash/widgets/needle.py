"""Needle: modello locale per function calling, servito in HTTP dal servizio `needle`.

Il widget tiene solo lo stato: se il servizio risponde, la frase inviata e la funzione che il
modello ha riconosciuto. Le richieste partono in un thread, così il disegno non aspetta mai la
rete. Tocco su una frase (o A): la invia a `POST /complete`.  B: sceglie la frase seguente.
Le frasi libere (dal telefono, `dash/voce.py`) passano da `chiedi`.
"""
from __future__ import annotations

import json
import logging
import socket
import threading
import time
from collections.abc import Hashable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Callable
from urllib import error, request
from urllib.parse import urlsplit

from .. import azioni, frasi
from .base import Widget

log = logging.getLogger(__name__)

CHECK_S = 5.0   # ogni quanto si controlla che il servizio sia raggiungibile
FLASH_S = 0.3   # evidenza dell'ultima frase toccata
ESITO_MAX = 40  # caratteri dell'esito che stanno nell'intestazione a 480 px
RECENTE_S = 6.0  # quanto dura la faccia del bot dopo una risposta (contento, errore, dubbio)

PostJson = Callable[[str, dict[str, Any], float], dict[str, Any]]


@dataclass(frozen=True)
class Risposta:
    """Esito di una frase: funzioni riconosciute (`nome(arg=valore)`), confidenza, tempo."""
    domanda: str
    chiamate: tuple[str, ...] = ()
    confidenza: float | None = None
    ms: int = 0
    errore: str = ""
    esito: str = ""   # cosa ha fatto il dashboard ("timer 5' avviato"), scritto da App
    t: float = 0.0    # quando è arrivata (orologio del widget): il bot ricorda l'esito per poco


def post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    """POST con corpo JSON, risposta JSON (oggetto)."""
    req = request.Request(url, data=json.dumps(payload).encode("utf-8"),
                          headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - solo http:// dalla config
        data = json.loads(resp.read().decode("utf-8") or "{}")
    if not isinstance(data, dict):
        raise ValueError("risposta non valida")
    return data


def chiamata_str(call: dict[str, Any]) -> str:
    """`{"name": "get_weather", "arguments": {"city": "Roma"}}` → `get_weather(city=Roma)`."""
    args = call.get("arguments")
    inner = ", ".join(f"{k}={v}" for k, v in args.items()) if isinstance(args, dict) else ""
    return f"{call.get('name', '?')}({inner})"


def raw_calls(data: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Le funzioni riconosciute come (nome, argomenti), da eseguire nel dashboard."""
    out: list[tuple[str, dict[str, Any]]] = []
    for c in data.get("function_calls") or []:
        if isinstance(c, dict) and isinstance(c.get("name"), str):
            args = c.get("arguments")
            out.append((c["name"], args if isinstance(args, dict) else {}))
    return out


def parse(domanda: str, data: dict[str, Any], ms: int) -> Risposta:
    """Risposta del servizio → `Risposta`; niente funzioni riconosciute è un esito, non un errore."""
    calls = [chiamata_str(c) for c in data.get("function_calls") or [] if isinstance(c, dict)]
    conf = data.get("confidence")
    errore = str(data.get("error") or "") if data.get("success") is False else ""
    return Risposta(domanda, tuple(calls), float(conf) if isinstance(conf, (int, float)) else None,
                    ms, errore)


class NeedleWidget(Widget):
    name = "needle"
    has_action = True
    tap_action = False  # fuori dai bottoni il tocco non fa nulla: A invia la frase scelta

    def __init__(self, cfg: dict[str, Any], clock: Callable[[], float] = time.monotonic,
                 post: PostJson = post_json) -> None:
        super().__init__(cfg)
        self.url = str(cfg.get("url", "http://127.0.0.1:8090")).rstrip("/")
        self.timeout_s = max(1.0, float(cfg.get("timeout_s", 15)))
        self.reset = bool(cfg.get("reset", True))  # ogni frase è indipendente dalle precedenti
        self.queries: list[str] = [str(q) for q in cfg.get("queries") or [] if str(q).strip()]
        self.esegui = bool(cfg.get("esegui", True))   # False: la scheda mostra e basta
        self.soglia = float(cfg.get("soglia", 0.6))   # sotto questa confidenza non si esegue
        self.soglia_pagine = float(cfg.get("soglia_pagine", 0.35))  # come sopra, se apre solo una pagina
        self.soglia_luci = float(cfg.get("soglia_luci", 0.4))       # e per le luci (con controlli sul testo)
        self.naviga = bool(cfg.get("naviga", True))   # dopo l'azione si apre la pagina interessata
        self.regole = bool(cfg.get("regole", True))   # timer, sveglie e luci capiti dal codice, non dal modello
        self.azioni: list[dict[str, Any]] = [dict(a) for a in cfg.get("azioni") or []]
        self.stanze: frasi.Stanze | None = None       # nomi delle stanze Hue, li dà App
        self.umore_forzato = ""                       # anteprime e test: fissa la faccia del bot
        self._pending: list[tuple[str, dict[str, Any], str]] = []
        self.idx = 0
        self._clock = clock
        self._post = post
        self._lock = threading.Lock()
        self._online: bool | None = None       # None = non ancora controllato
        self._busy = False
        self._checking = False
        self._checked = -CHECK_S * 2
        self._last: Risposta | None = None
        self.risposte = 0          # risposte arrivate: il telefono capisce quando c'è la sua
        self._in_corso = 0         # chiamate prese da App e non ancora concluse da `set_esito`
        self._hit = -1
        self._hit_at = -FLASH_S
        self.demo = False

    def load_demo(self) -> None:
        """Stato fisso per le anteprime: servizio acceso e una risposta già arrivata."""
        self.demo = True
        with self._lock:
            self._online = True
            self._last = Risposta(self.queries[0] if self.queries else "", ("get_weather(city=Ventotene)",),
                                  0.95, 2210, esito="apro il meteo", t=self._clock())

    # --- stato -----------------------------------------------------------
    def snapshot(self) -> tuple[bool | None, bool, Risposta | None]:
        """(servizio raggiungibile, richiesta in corso, ultima risposta)."""
        with self._lock:
            return self._online, self._busy, self._last

    def stato(self) -> str:
        online, busy, _ = self.snapshot()
        if busy:
            return "penso…"
        return "pronto" if online else ("offline" if online is False else "controllo…")

    def umore(self) -> str:
        """Faccia del bot: offline, controllo, penso, pronto, fatto, dubbio o errore.

        L'esito (fatto, dubbio, errore) si vede per `RECENTE_S` secondi dopo la risposta; poi il
        bot torna "pronto". Nelle anteprime (`demo`) resta quello dell'ultima risposta.
        """
        if self.umore_forzato:
            return self.umore_forzato
        online, busy, last = self.snapshot()
        if online is False:
            return "offline"
        if online is None:
            return "controllo"
        if busy:
            return "penso"
        if last is None or (not self.demo and self._clock() - last.t >= RECENTE_S):
            return "pronto"
        if last.errore or last.esito.startswith("errore"):
            return "errore"
        if not last.chiamate or last.esito.startswith("confidenza bassa"):
            return "dubbio"
        return "fatto"

    def flashing(self) -> int:
        """Indice dell'ultima frase toccata, per un attimo; altrimenti -1."""
        return self._hit if self._clock() - self._hit_at < FLASH_S else -1

    def state_key(self, now: datetime) -> Hashable:
        online, busy, last = self.snapshot()
        return (online, busy, last, self.idx, self.flashing(), self.umore())

    # --- rete ------------------------------------------------------------
    def update(self, now: datetime) -> None:
        if self.demo or self._checking or self._clock() - self._checked < CHECK_S:
            return
        self._checking = True
        self._checked = self._clock()
        threading.Thread(target=self._check, name="needle-check", daemon=True).start()

    def _check(self) -> None:
        """Il servizio è acceso se accetta una connessione TCP: niente richieste al modello."""
        parts = urlsplit(self.url)
        try:
            socket.create_connection((parts.hostname or "127.0.0.1", parts.port or 80), 2).close()
            up = True
        except OSError:
            up = False
        with self._lock:
            self._online = up
        self._checking = False

    def ask(self, i: int) -> None:
        """Invia la frase `i` al modello (in un thread); ignorata se ce n'è una in corso."""
        if 0 <= i < len(self.queries) and self.chiedi(self.queries[i]):
            self._hit, self._hit_at = i, self._clock()

    def chiedi(self, domanda: str) -> bool:
        """Invia una frase qualsiasi (in un thread); False se ce n'è già una in corso o se il
        servizio è spento e la frase non la capisce l'interprete da solo."""
        domanda = domanda.strip()
        if not domanda:
            return False
        # senza il servizio le frasi che l'interprete capisce da sole funzionano lo stesso
        fuori = self._online is False and not (self.regole and frasi.interpreta(
            domanda, self.azioni))
        with self._lock:
            if self._busy or fuori:
                return False
            self._busy = True
        threading.Thread(target=self._run, args=(domanda,), name="needle-ask",
                         daemon=True).start()
        return True

    def in_attesa(self) -> bool:
        """True finché l'ultima frase non ha un esito completo (modello, poi azioni del dashboard)."""
        with self._lock:
            return self._busy or bool(self._pending) or self._in_corso > 0

    def _regole(self, domanda: str) -> list[tuple[str, dict[str, Any]]] | None:
        """Le chiamate che l'interprete di frasi ricava da solo; None se serve il modello."""
        if not self.regole:
            return None
        try:
            return frasi.interpreta(domanda, self.azioni, self._nomi_stanze)
        except (OSError, RuntimeError, ValueError) as exc:   # Hue spento: l'azione lo dirà
            log.debug("needle: regole non applicabili: %s", exc)
            return None

    def _nomi_stanze(self) -> list[str] | None:
        """Nomi delle stanze Hue; None se il bridge non c'è o non risponde."""
        if self.stanze is None:
            return None
        try:
            return self.stanze()
        except (OSError, RuntimeError, ValueError):
            return None

    def _run(self, domanda: str) -> None:
        t0 = self._clock()
        try:
            regole = self._regole(domanda)
            if regole:      # capita dal codice: niente modello, nessuna attesa
                data = {"function_calls": [{"name": n, "arguments": a} for n, a in regole],
                        "confidence": 1.0, "success": True}
                risposta = parse(domanda, data, round((self._clock() - t0) * 1000))
                calls = raw_calls(data)
            else:
                if self.reset:
                    try:
                        self._post(f"{self.url}/reset", {}, self.timeout_s)
                    except (OSError, ValueError, error.URLError) as exc:
                        log.debug("needle: reset non riuscito: %s", exc)
                data = self._post(f"{self.url}/complete", {"input": domanda}, self.timeout_s)
                risposta = parse(domanda, data, round((self._clock() - t0) * 1000))
                calls = raw_calls(data)
        except (OSError, ValueError, error.URLError) as exc:  # timeout, rifiuto, JSON rotto
            log.warning("needle: %s", exc)
            risposta, calls = Risposta(domanda, errore="servizio non risponde"), []
        if calls and self.esegui:
            conf = risposta.confidenza if risposta.confidenza is not None else 0.0
            soglie = {"pagina": self.soglia_pagine, "luci": self.soglia_luci, "stato": self.soglia}
            sicure = [c for c in calls if conf >= soglie[azioni.categoria(c[0])]]
            if not sicure:
                risposta = replace(risposta, esito="confidenza bassa: non eseguo")
            calls = sicure
        else:
            calls = []
        with self._lock:
            # le esegue App nel ciclo principale, non questo thread; serve anche la frase detta
            self._pending.extend((nome, args, domanda) for nome, args in calls)
            self._last = replace(risposta, t=self._clock())
            self.risposte += 1
            self._busy = False
            if risposta.errore == "servizio non risponde":
                self._online = False

    def take_calls(self) -> list[tuple[str, dict[str, Any], str]]:
        """(funzione, argomenti, frase) riconosciuti e non ancora eseguiti; li svuota (App, a ogni giro)."""
        with self._lock:
            out, self._pending = self._pending, []
            self._in_corso += len(out)
        return out

    def set_esito(self, text: str) -> None:
        """Scrive nell'ultima risposta cosa ha fatto il dashboard (più azioni: separate da " · ")."""
        with self._lock:
            if self._last is not None:
                unite = f"{self._last.esito} · {text}" if self._last.esito else text
                self._last = replace(self._last, esito=unite[:ESITO_MAX])
            self._in_corso = max(0, self._in_corso - 1)

    # --- ingressi --------------------------------------------------------
    def on_hit(self, hit: str, now: datetime) -> None:
        kind, _, arg = hit.partition(":")
        if kind == "q" and arg.isdigit() and self.queries:
            self.idx = int(arg) % len(self.queries)
            self.ask(self.idx)

    def on_action(self, now: datetime) -> None:
        if self.queries:
            self.ask(self.idx)

    def on_back(self, now: datetime) -> None:
        if self.queries:
            self.idx = (self.idx + 1) % len(self.queries)
