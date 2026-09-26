"""Scheda "+": aggiunge e toglie pagine senza modificare i file a mano.

A: esegue la voce scelta (aggiunge o toglie una pagina).  B: passa alla voce seguente.
Le voci sono costruite a ogni lettura dalle pagine esistenti, che l'app fornisce con i callback.
"""
from __future__ import annotations

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
}
ORDINE = ("timer", "alarm", "clock", "weather", "system")


@dataclass(frozen=True)
class Voce:
    """Una riga del catalogo: aggiunge un tipo di widget o toglie una pagina esistente."""
    azione: str   # "add" oppure "del"
    valore: str   # tipo di widget ("timer") oppure chiave della pagina da togliere
    label: str


class NewWidget(Widget):
    name = "new"
    has_action = True

    def __init__(self, cfg: dict[str, Any]) -> None:
        super().__init__(cfg)
        tipi = [t for t in cfg.get("tipi") or ORDINE if t in ETICHETTE]
        self.tipi: list[str] = tipi or list(ORDINE)
        self.idx = 0
        # Impostati da App: elenco delle pagine togglibili e azioni sulle pagine.
        self.pagine: Callable[[], list[tuple[str, str]]] = list
        self.aggiungi: Callable[[str], None] = lambda tipo: None
        self.togli: Callable[[str], None] = lambda chiave: None

    def voci(self) -> list[Voce]:
        """Catalogo: prima i tipi da aggiungere, poi le pagine da togliere."""
        voci = [Voce("add", t, ETICHETTE[t].lower()) for t in self.tipi]
        voci += [Voce("del", chiave, nome.lower()) for chiave, nome in self.pagine()]
        return voci

    def scelta(self) -> Voce | None:
        voci = self.voci()
        return voci[self.idx % len(voci)] if voci else None

    def on_back(self, now: datetime) -> None:
        voci = self.voci()
        self.idx = (self.idx + 1) % len(voci) if voci else 0

    def on_select(self, i: int) -> None:
        voci = self.voci()
        if voci:
            self.idx = i % len(voci)

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
        return (self.idx, tuple(self.pagine()))
