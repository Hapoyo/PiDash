"""Interfaccia comune dei widget: stato e dati; il disegno è in `dash/render/pages/`."""
from __future__ import annotations

from collections.abc import Hashable
from datetime import datetime
from typing import Any

class Widget:
    """Sorgente di dati del dashboard: aggiorna il proprio stato e risponde ai pulsanti."""

    name: str = "widget"
    has_action: bool = False  # True se A/B fanno qualcosa (timer, sveglia)

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg

    def update(self, now: datetime) -> None:
        """Aggiorna lo stato interno (chiamato a ogni tick)."""

    def state_key(self, now: datetime) -> Hashable:
        """Tutto ciò che cambia il disegno: se non cambia, il fotogramma non si ridisegna."""
        return now.strftime("%Y%m%d%H%M")

    def on_action(self, now: datetime) -> None:
        """Pulsante A."""

    def on_back(self, now: datetime) -> None:
        """Pulsante B."""

    def on_select(self, i: int) -> None:
        """Tocco su una voce selezionabile della pagina (scheda "+")."""

    def alert(self) -> str | None:
        """Testo di allarme se il widget richiede attenzione, altrimenti None."""
        return None

    def close(self) -> None:
        """Rilascia risorse (thread, file)."""

