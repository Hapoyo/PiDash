"""Orologio: alba/tramonto alla posizione corrente e avanzamento della giornata."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from ..astro import hhmm, sun_times
from ..location import Location
from .base import Widget

PROGRESS_MODES = ("day", "daylight", "hour")


class ClockWidget(Widget):
    name = "clock"

    def __init__(self, cfg: dict[str, Any], location: Location | None = None) -> None:
        super().__init__(cfg)
        self.location = location
        self.progress_mode = cfg.get("progress", "day")
        if self.progress_mode not in PROGRESS_MODES:
            raise ValueError(f"clock.progress deve essere uno di {PROGRESS_MODES}")
        self._sun: tuple[tuple[date, float, float], datetime | None, datetime | None] | None = None

    # --- dati ------------------------------------------------------------
    def sun_dt(self, now: datetime) -> tuple[datetime | None, datetime | None] | None:
        """(alba, tramonto) di oggi alla posizione corrente; None senza posizione."""
        if self.location is None:
            return None
        _, lat, lon = self.location.snapshot()
        key = (now.date(), round(lat, 3), round(lon, 3))
        if self._sun is None or self._sun[0] != key:
            rise, sets = sun_times(now.date(), lat, lon)
            self._sun = (key, rise, sets)
        return self._sun[1], self._sun[2]

    def sun(self, now: datetime) -> tuple[str, str] | None:
        s = self.sun_dt(now)
        return (hhmm(s[0]), hhmm(s[1])) if s else None

    def progress(self, now: datetime) -> tuple[str, float]:
        """(etichetta, frazione 0…1) secondo `clock.progress`."""
        if self.progress_mode == "hour":
            return "ORA", (now.minute * 60 + now.second) / 3600
        if self.progress_mode == "daylight":
            s = self.sun_dt(now)
            if s and s[0] and s[1]:
                rise, sets = (t.replace(tzinfo=None) for t in (s[0], s[1]))
                if now <= rise:
                    return "LUCE", 0.0
                return "LUCE", min(1.0, (now - rise) / (sets - rise))
        minutes = now.hour * 60 + now.minute
        return "GIORNATA", minutes / 1440

