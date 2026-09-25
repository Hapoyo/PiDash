"""Registro dei widget disponibili."""
from __future__ import annotations

from typing import Any

from ..location import Location
from .alarm import AlarmWidget
from .base import Widget
from .clock import ClockWidget
from .system import SystemWidget
from .timer import TimerWidget
from .weather import WeatherWidget

WIDGET_NAMES: set[str] = {"clock", "timer", "alarm", "weather", "system"}


def build_widgets(names: set[str], cfg: dict[str, Any]) -> dict[str, Widget]:
    """Istanzia una sola volta ogni widget usato nelle pagine, più quelli da cui dipendono
    Posizione condivisa fra orologio e meteo."""
    names = set(names)
    location = Location(cfg["location"], cfg["weather"].get("cache_dir", "out"))
    built: dict[str, Widget] = {}
    order = ["weather", "alarm", "clock", "timer", "system"]
    for n in sorted(names, key=order.index):
        if n == "weather":
            built[n] = WeatherWidget(cfg["weather"], location)
        elif n == "alarm":
            built[n] = AlarmWidget(cfg["alarm"])
        elif n == "clock":
            built[n] = ClockWidget(cfg["clock"], location)
        elif n == "timer":
            built[n] = TimerWidget(cfg["timer"])
        elif n == "system":
            built[n] = SystemWidget(cfg["system"])
    return built


__all__ = ["Widget", "WIDGET_NAMES", "build_widgets"]
