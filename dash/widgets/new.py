"""Scheda Impostazioni (linguetta con l'ingranaggio): schede, luminosità, touch, spegnimento.

Ogni voce delle schede fa da interruttore: se la scheda non c'è la aggiunge, se c'è la toglie,
quindi una sola scheda per tipo. Col tocco ogni bottone agisce subito; coi tasti A esegue la
voce scelta e B passa alla seguente. Lo spegnimento chiede un secondo tocco di conferma.
"""
from __future__ import annotations

import time
from collections.abc import Hashable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from .base import Widget

# Nome della linguetta proposto per ogni tipo di widget (senza numero).
ETICHETTE: dict[str, str] = {
    "timer": "Timer",
    "alarm": "Sveglia",
    "clock": "Orologio",
    "weather": "Meteo",
    "system": "Sistema",
    "needle": "Needle",
}
ORDINE = ("timer", "alarm", "needle")  # schede opzionali: le altre pagine stanno in config.json
CONFERMA_S = 4.0             # tempo per il secondo tocco su "spegni"


@dataclass(frozen=True)
class Voce:
    """Una riga del catalogo: aggiunge il tipo, oppure toglie la pagina già presente."""
    azione: str   # "add" oppure "del"
    valore: str   # tipo di widget ("timer") oppure chiave della pagina da togliere
    label: str


class NewWidget(Widget):
    name = "new"
    has_action = True
    tap_action = False  # fuori dai bottoni il tocco non fa nulla: A esegue la voce scelta

    def __init__(self, cfg: dict[str, Any], clock: Callable[[], float] = time.monotonic) -> None:
        super().__init__(cfg)
        tipi = [t for t in cfg.get("tipi") or ORDINE if t in ETICHETTE]
        self.tipi: list[str] = tipi or list(ORDINE)
        self.idx = 0
        self._clock = clock
        self._armato = -CONFERMA_S * 2
        # Impostati da App: pagine presenti ({tipo: chiave}) e azioni sul dashboard.
        self.pagine: Callable[[], dict[str, str]] = dict
        self.aggiungi: Callable[[str], None] = lambda tipo: None
        self.togli: Callable[[str], None] = lambda chiave: None
        self.luce: Callable[[], int] = lambda: 100
        self.regola_luce: Callable[[int], None] = lambda delta: None
        self.calibra: Callable[[], None] = lambda: None
        self.spegni: Callable[[], None] = lambda: None
        self.avviso: Callable[[], str] = lambda: ""   # messaggio breve (es. "touch calibrato")
        self.info: Callable[[], str] = lambda: ""     # riga in fondo (versione, tipo di luce)
        self.alimentazione: Callable[[], Any] = lambda: None  # PowerMonitor, se c'è

    def voci(self) -> list[Voce]:
        """Una voce per tipo: "aggiungi" se manca, "togli" se la scheda è già nello schedario."""
        presenti = self.pagine()
        return [Voce("del", presenti[t], ETICHETTE[t].lower()) if t in presenti
                else Voce("add", t, ETICHETTE[t].lower()) for t in self.tipi]

    def scelta(self) -> Voce | None:
        voci = self.voci()
        return voci[self.idx % len(voci)] if voci else None

    def armato(self) -> bool:
        """True nei secondi in cui un altro tocco su "spegni" spegne davvero."""
        return self._clock() - self._armato < CONFERMA_S

    def on_back(self, now: datetime) -> None:
        voci = self.voci()
        self.idx = (self.idx + 1) % len(voci) if voci else 0

    def on_hit(self, hit: str, now: datetime) -> None:
        """Tocco su un bottone: voce delle schede, luce ±, calibrazione, spegnimento."""
        kind, _, arg = hit.partition(":")
        if kind == "voce":
            voci = self.voci()
            if voci:
                self.idx = int(arg) % len(voci)
                self.on_action(now)
        elif kind == "luce":
            self.regola_luce(int(arg))
        elif kind == "calibra":
            self.calibra()
        elif kind == "spegni":
            if self.armato():
                self._armato = -CONFERMA_S * 2
                self.spegni()
            else:
                self._armato = self._clock()

    def on_action(self, now: datetime) -> None:
        voce = self.scelta()
        if voce is None:
            return
        if voce.azione == "add":
            self.aggiungi(voce.valore)
        else:
            self.togli(voce.valore)
        self.idx = 0

    def state_key(self, now: datetime) -> Hashable:
        power = self.alimentazione()
        return (self.idx, tuple(sorted(self.pagine())), self.luce(), self.armato(), self.avviso(),
                self.info(), power.state_key() if power is not None else None)
