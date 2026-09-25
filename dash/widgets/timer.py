"""Timer a conto alla rovescia con preset.

A: avvia / pausa / riprendi / conferma fine.  B: cambia preset (fermo) o azzera.
"""
from __future__ import annotations

import math
import time
from datetime import datetime
from enum import Enum
from collections.abc import Hashable
from typing import Any, Callable

from .base import Widget


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
        presets = [int(p) for p in cfg.get("presets_s", [300]) if int(p) > 0]
        if not presets:
            raise ValueError("timer.presets_s deve contenere almeno un valore > 0")
        self.presets = presets
        self.step_s = max(1, int(cfg.get("step_s", 10)))
        self._clock = clock
        self.preset_idx = 0
        self.state = TimerState.IDLE
        self._deadline = 0.0
        self._remaining = float(self.presets[0])
        # Etichetta per preset, es. {"300": "PARTENZA"} (sequenza di partenza di regata).
        self.labels = {int(k): str(v).upper() for k, v in (cfg.get("labels") or {}).items()}

    def label(self) -> str:
        """Etichetta mostrata sotto la barra: nome del preset o stato."""
        if self.state is TimerState.PAUSED:
            return "PAUSA"
        if self.state is TimerState.DONE:
            return "FINE"
        return self.labels.get(self.duration, self.state.value)

    @property
    def duration(self) -> int:
        return self.presets[self.preset_idx]

    def remaining(self) -> float:
        if self.state is TimerState.RUNNING:
            return max(0.0, self._deadline - self._clock())
        return self._remaining

    def shown_remaining(self) -> int:
        """Secondi mostrati, arrotondati per eccesso al passo (limita i refresh e-ink)."""
        rem = self.remaining()
        if self.state is TimerState.RUNNING:
            return int(math.ceil(rem / self.step_s) * self.step_s)
        return int(math.ceil(rem))

    def update(self, now: datetime) -> None:
        if self.state is TimerState.RUNNING and self.remaining() <= 0:
            self.state = TimerState.DONE
            self._remaining = 0.0

    def on_action(self, now: datetime) -> None:
        if self.state is TimerState.IDLE:
            self._deadline = self._clock() + self.duration
            self.state = TimerState.RUNNING
        elif self.state is TimerState.RUNNING:
            self._remaining = self.remaining()
            self.state = TimerState.PAUSED
        elif self.state is TimerState.PAUSED:
            self._deadline = self._clock() + self._remaining
            self.state = TimerState.RUNNING
        else:  # DONE: conferma
            self._reset()

    def on_back(self, now: datetime) -> None:
        if self.state is TimerState.IDLE:
            self.preset_idx = (self.preset_idx + 1) % len(self.presets)
        self._reset()

    def _reset(self) -> None:
        self.state = TimerState.IDLE
        self._remaining = float(self.duration)

    def state_key(self, now: datetime) -> Hashable:
        return (self.state, self.shown_remaining(), self.preset_idx)

    def alert(self) -> str | None:
        return "TIMER SCADUTO" if self.state is TimerState.DONE else None

