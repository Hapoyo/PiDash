"""Sveglie settimanali.

A: spegne la sveglia che suona, altrimenti arma/disarma tutte.  B: nessuna azione.
"""
from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from ..layout import GIORNI
from .base import Widget

MAX_ALARMS = 10  # le sveglie create da Needle non si tolgono dallo schermo: il numero è limitato


@dataclass(frozen=True)
class Alarm:
    hour: int
    minute: int
    days: frozenset[int]  # 0 = lunedì
    enabled: bool = True

    @classmethod
    def from_cfg(cls, d: dict[str, Any]) -> Alarm:
        hh, mm = (int(p) for p in d["time"].split(":"))
        days = frozenset(d.get("days", range(7)))
        return cls(hh, mm, days, bool(d.get("enabled", True)))

    def to_cfg(self) -> dict[str, Any]:
        """Voce di `alarm.alarms` in config.local.json."""
        return {"time": f"{self.hour:02d}:{self.minute:02d}", "days": sorted(self.days),
                "enabled": self.enabled}

    def label_days(self) -> str:
        if self.days == frozenset(range(7)):
            return "TUTTI I GG"
        if self.days == frozenset(range(5)):
            return "LUN-VEN"
        if self.days == frozenset({5, 6}):
            return "SAB-DOM"
        return " ".join(GIORNI[d][:2] for d in sorted(self.days))


class AlarmWidget(Widget):
    name = "alarm"
    has_action = True

    def __init__(self, cfg: dict[str, Any]) -> None:
        super().__init__(cfg)
        self.alarms = [Alarm.from_cfg(a) for a in cfg.get("alarms", [])]
        self.ring_max = timedelta(minutes=int(cfg.get("ring_max_min", 10)))
        self.armed = True
        self.ringing: Alarm | None = None
        self._ring_start: datetime | None = None
        self._handled: set[str] = set()

    def add_alarm(self, hour: int, minute: int, days: frozenset[int] | None = None) -> Alarm:
        """Sveglia a quell'ora (comando di Needle), ogni giorno se `days` manca (0 = lunedì).

        Se c'è già una sveglia alla stessa ora la sostituisce, e arma tutto.
        """
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError(f"orario fuori range: {hour:02d}:{minute:02d}")
        if days is not None and (not days or not days <= frozenset(range(7))):
            raise ValueError("giorni non validi")
        alarm = Alarm(hour, minute, days if days is not None else frozenset(range(7)))
        same = [i for i, a in enumerate(self.alarms) if (a.hour, a.minute) == (hour, minute)]
        if same:
            self.alarms[same[0]] = alarm
        elif len(self.alarms) >= MAX_ALARMS:
            raise ValueError(f"al massimo {MAX_ALARMS} sveglie")
        else:
            self.alarms.append(alarm)
        self.armed = True
        return alarm

    def remove_alarms(self, hour: int | None = None, minute: int | None = None) -> int:
        """Toglie la sveglia a quell'ora, o tutte se l'ora manca (comando di Needle); quante ne ha tolte."""
        tenute = [a for a in self.alarms
                  if hour is not None and (a.hour, a.minute) != (hour, minute)]
        tolte = len(self.alarms) - len(tenute)
        self.alarms = tenute
        if self.ringing is not None and self.ringing not in tenute:
            self.ringing = None
        return tolte

    @staticmethod
    def _key(a: Alarm, now: datetime) -> str:
        return f"{now:%Y-%m-%d}T{a.hour:02d}:{a.minute:02d}"

    def next_alarm(self, now: datetime) -> tuple[Alarm, datetime] | None:
        """Prossima sveglia attiva entro 7 giorni."""
        best: tuple[Alarm, datetime] | None = None
        for a in self.alarms:
            if not a.enabled:
                continue
            for off in range(8):
                day = now + timedelta(days=off)
                when = day.replace(hour=a.hour, minute=a.minute, second=0, microsecond=0)
                if when.weekday() in a.days and when > now:
                    if best is None or when < best[1]:
                        best = (a, when)
                    break
        return best

    def update(self, now: datetime) -> None:
        if self.ringing and self._ring_start and now - self._ring_start >= self.ring_max:
            self.ringing = None
        if self.ringing or not self.armed:
            return
        for a in self.alarms:
            key = self._key(a, now)
            if (a.enabled and now.weekday() in a.days and now.hour == a.hour
                    and now.minute == a.minute and key not in self._handled):
                self._handled.add(key)
                self.ringing = a
                self._ring_start = now
                break
        if len(self._handled) > 64:  # evita crescita illimitata
            self._handled = {k for k in self._handled if k.startswith(f"{now:%Y-%m-%d}")}

    def on_action(self, now: datetime) -> None:
        if self.ringing:
            self.ringing = None
        else:
            self.armed = not self.armed

    def state_key(self, now: datetime) -> Hashable:
        return (self.armed, self.ringing, now.strftime("%Y%m%d%H%M"))

    def alert(self) -> str | None:
        if self.ringing:
            return f"SVEGLIA {self.ringing.hour:02d}:{self.ringing.minute:02d}"
        return None

