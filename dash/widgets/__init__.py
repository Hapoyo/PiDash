"""Registro dei widget disponibili e fabbrica delle istanze."""
from __future__ import annotations

from typing import Any

from ..location import Location
from .alarm import AlarmWidget
from .base import Widget
from .clock import ClockWidget
from .needle import NeedleWidget
from .new import ETICHETTE, NewWidget
from .system import SystemWidget
from .timer import TimerWidget
from .weather import WeatherWidget

WIDGET_NAMES: set[str] = {"clock", "timer", "alarm", "weather", "system", "needle", "new"}


class WidgetFactory:
    """Crea i widget di una pagina alla volta, con la posizione condivisa fra orologio e meteo."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        self.location = Location(cfg["location"], cfg["weather"].get("cache_dir", "out"))

    def make(self, kind: str) -> Widget:
        """Nuova istanza del widget `kind` (più pagine dello stesso tipo sono indipendenti)."""
        cfg = self.cfg
        if kind == "weather":
            return WeatherWidget(cfg["weather"], self.location)
        if kind == "clock":
            return ClockWidget(cfg["clock"], self.location)
        if kind == "alarm":
            return AlarmWidget(cfg["alarm"])
        if kind == "timer":
            return TimerWidget(cfg["timer"])
        if kind == "system":
            return SystemWidget(cfg["system"])
        if kind == "needle":
            return NeedleWidget(cfg["needle"])
        if kind == "new":
            return NewWidget(cfg.get("new") or {})
        raise ValueError(f"widget sconosciuto: {kind!r}")


__all__ = ["ETICHETTE", "Widget", "WidgetFactory", "WIDGET_NAMES"]
