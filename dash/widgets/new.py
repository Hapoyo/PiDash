"""Scheda "+": elenco delle schede che si possono aggiungere (timer, sveglia).

Ogni voce fa da interruttore: se la scheda non c'è la aggiunge, se c'è la toglie — quindi una
sola scheda per tipo. A esegue la voce scelta, B passa alla seguente.
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
ORDINE = ("timer", "alarm")  # schede opzionali: le altre pagine stanno in config.json


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

    def __init__(self, cfg: dict[str, Any]) -> None:
        super().__init__(cfg)
        tipi = [t for t in cfg.get("tipi") or ORDINE if t in ETICHETTE]
        self.tipi: list[str] = tipi or list(ORDINE)
        self.idx = 0
        # Impostati da App: pagine presenti ({tipo: chiave}) e azioni sullo schedario.
        self.pagine: Callable[[], dict[str, str]] = dict
        self.aggiungi: Callable[[str], None] = lambda tipo: None
        self.togli: Callable[[str], None] = lambda chiave: None

    def voci(self) -> list[Voce]:
        """Una voce per tipo: "aggiungi" se manca, "togli" se la scheda è già nello schedario."""
        presenti = self.pagine()
        return [Voce("del", presenti[t], ETICHETTE[t].lower()) if t in presenti
                else Voce("add", t, ETICHETTE[t].lower()) for t in self.tipi]

    def scelta(self) -> Voce | None:
        voci = self.voci()
        return voci[self.idx % len(voci)] if voci else None

    def on_back(self, now: datetime) -> None:
        voci = self.voci()
        self.idx = (self.idx + 1) % len(voci) if voci else 0

    def on_hit(self, hit: str, now: datetime) -> None:
        """Tocco su una voce: la esegue subito (niente "seleziona, poi conferma")."""
        kind, _, arg = hit.partition(":")
        voci = self.voci()
        if kind == "voce" and voci:
            self.idx = int(arg) % len(voci)
            self.on_action(now)

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
        return (self.idx, tuple(sorted(self.pagine())))
