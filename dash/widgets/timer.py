"""Timer a conto alla rovescia: il tempo si compone sommando i bottoni.

Bottoni (tocco): "−" toglie un minuto, ogni preset si somma a ogni tocco, "C" azzera.
Tocco sul tempo o A: avvia / pausa / riprendi / conferma fine.  B: somma il primo preset.
"""
from __future__ import annotations

import math
import time
from datetime import datetime
from enum import Enum
from collections.abc import Hashable
from typing import Any, Callable

from .base import Widget

STEP_DOWN_S = 60   # quanto toglie il bottone "−"
FLASH_S = 0.3      # evidenza dell'ultimo bottone toccato


class TimerState(Enum):
    IDLE = "PRONTO"
    RUNNING = "IN CORSO"
    PAUSED = "PAUSA"
    DONE = "FINE"


class TimerWidget(Widget):
    name = "timer"
    has_action = True

    def __init__(self, cfg: dict[str, Any], clock: Callable[[], float] = time.monotonic) -> None:
        super().__init__(cfg)
        given = [int(p) for p in cfg.get("presets_s", [300]) if int(p) > 0]
        if not given:
            raise ValueError("timer.presets_s deve contenere almeno un valore > 0")
        self.presets = sorted(set(given))
        self.step_s = max(1, int(cfg.get("step_s", 10)))
        self._clock = clock
        self.state = TimerState.IDLE
        self._deadline = 0.0
        # Etichetta per durata, es. {"300": "PARTENZA"} (sequenza di partenza di regata).
        self.labels = {int(k): str(v).upper() for k, v in (cfg.get("labels") or {}).items()}
        # all'accensione: la prima durata con un nome (la partenza), altrimenti il primo preset
        self._set_s = next((p for p in given if p in self.labels), given[0])
        self._remaining = float(self._set_s)
        self._hit = ""
        self._hit_at = -FLASH_S

    def buttons(self) -> list[tuple[str, str]]:
        """(id, testo) dei bottoni della riga, da sinistra: − · +preset… · C."""
        def short(s: int) -> str:
            return f"{s // 60}'" if s % 60 == 0 else f'{s}"'
        return ([("sub", f"−{short(STEP_DOWN_S)}")]
                + [(f"add:{p}", f"+{short(p)}") for p in self.presets] + [("clear", "C")])

    def label(self) -> str:
        """Etichetta mostrata sotto la barra: nome della durata o stato."""
        if self.state is TimerState.PAUSED:
            return "PAUSA"
        if self.state is TimerState.DONE:
            return "FINE"
        return self.labels.get(self.duration, self.state.value)

    @property
    def duration(self) -> int:
        """Tempo impostato con i bottoni (la barra si misura su questo)."""
        return self._set_s

    def remaining(self) -> float:
        if self.state is TimerState.RUNNING:
            return max(0.0, self._deadline - self._clock())
        return self._remaining

    def shown_remaining(self) -> int:
        """Secondi mostrati, arrotondati per eccesso al passo (limita i ridisegni)."""
        rem = self.remaining()
        if self.state is TimerState.RUNNING:
            return int(math.ceil(rem / self.step_s) * self.step_s)
        return int(math.ceil(rem))

    def flashing(self) -> str:
        """Id del bottone appena toccato (per l'evidenza), "" dopo `FLASH_S`."""
        return self._hit if self._clock() - self._hit_at < FLASH_S else ""

    def update(self, now: datetime) -> None:
        if self.state is TimerState.RUNNING and self.remaining() <= 0:
            self.state = TimerState.DONE
            self._remaining = 0.0

    def on_hit(self, hit: str, now: datetime) -> None:
        kind, _, arg = hit.partition(":")
        if kind == "sub":
            self._adjust(-STEP_DOWN_S)
        elif kind == "add":
            self._adjust(int(arg))
        elif kind == "clear":
            self.state = TimerState.IDLE
            self._set_s, self._remaining = 0, 0.0
        else:
            return
        self._hit, self._hit_at = hit, self._clock()

    def _adjust(self, delta: int) -> None:
        """Somma o toglie tempo; mentre scorre si sposta la scadenza."""
        if self.state is TimerState.DONE:
            self._reset()
        self._set_s = max(0, self._set_s + delta)
        if self.state is TimerState.RUNNING:
            left = max(0.0, self.remaining() + delta)
            self._deadline = self._clock() + left
            self._set_s = max(self._set_s, math.ceil(left))
        elif self.state is TimerState.PAUSED:
            self._remaining = max(0.0, self._remaining + delta)
            self._set_s = max(self._set_s, math.ceil(self._remaining))
        else:
            self._remaining = float(self._set_s)

    def on_action(self, now: datetime) -> None:
        if self.state is TimerState.IDLE:
            if self._remaining <= 0:
                return  # niente tempo impostato: non parte
            self._deadline = self._clock() + self._remaining
            self.state = TimerState.RUNNING
        elif self.state is TimerState.RUNNING:
            self._remaining = self.remaining()
            self.state = TimerState.PAUSED
        elif self.state is TimerState.PAUSED:
            if self._remaining <= 0:
                self._reset()
                return
            self._deadline = self._clock() + self._remaining
            self.state = TimerState.RUNNING
        else:  # DONE: conferma, si torna al tempo impostato
            self._reset()

    def on_back(self, now: datetime) -> None:
        self.on_hit(f"add:{self.presets[0]}", now)

    def _reset(self) -> None:
        self.state = TimerState.IDLE
        self._remaining = float(self._set_s)

    def state_key(self, now: datetime) -> Hashable:
        return (self.state, self.shown_remaining(), self._set_s, self.flashing())

    def alert(self) -> str | None:
        return "TIMER SCADUTO" if self.state is TimerState.DONE else None
