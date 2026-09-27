"""Calibrazione del touch a schermo: quattro croci, un tocco su ciascuna.

Dai valori grezzi del controller nei quattro punti si ricavano gli estremi (`x_min`…`y_max`),
lo scambio degli assi e le inversioni che `TouchCalibration` usa: in pratica una retta per asse
(minimi quadrati), così un tocco un po' storto non rovina il risultato.
"""
from __future__ import annotations

import math
import time
from typing import Any, Callable

from ..inputs import Tap, frame_to_panel

# Croci nel fotogramma (0…1), in senso orario dall'angolo in alto a sinistra.
TARGETS = ((0.1, 0.12), (0.9, 0.12), (0.9, 0.88), (0.1, 0.88))
TIMEOUT_S = 30.0   # senza tocchi la calibrazione si annulla
MIN_SPAN = 300     # escursione grezza minima fra le croci (controller a 12 bit: 0…4095)
MIN_CORR = 0.9     # i quattro punti devono stare quasi su una retta per asse


def _fit(raw: list[float], pos: list[float]) -> tuple[float, float, float]:
    """Retta raw = a + b·pos: (valore a pos=0, valore a pos=1, correlazione)."""
    n = len(raw)
    mr, mp = sum(raw) / n, sum(pos) / n
    cov = sum((r - mr) * (p - mp) for r, p in zip(raw, pos))
    var_p = sum((p - mp) ** 2 for p in pos)
    var_r = sum((r - mr) ** 2 for r in raw)
    if var_p == 0 or var_r == 0:
        return mr, mr, 0.0
    b = cov / var_p
    a = mr - b * mp
    return a, a + b, cov / math.sqrt(var_p * var_r)


def solve(targets: list[tuple[float, float]], raws: list[tuple[int, int]]) -> dict[str, Any] | None:
    """Voci di `input.touch` dai punti del pannello (0…1) e dai valori grezzi; None se incoerenti."""
    us, vs = [t[0] for t in targets], [t[1] for t in targets]
    rx, ry = [float(r[0]) for r in raws], [float(r[1]) for r in raws]
    swap = abs(_fit(rx, vs)[2]) > abs(_fit(rx, us)[2])  # raw x segue l'asse verticale?
    src_u, src_v = (ry, rx) if swap else (rx, ry)
    u0, u1, cu = _fit(src_u, us)
    v0, v1, cv = _fit(src_v, vs)
    if min(abs(cu), abs(cv)) < MIN_CORR or min(abs(u1 - u0), abs(v1 - v0)) < MIN_SPAN:
        return None
    # estremi dell'asse grezzo che dà u (x sullo schermo) e di quello che dà v
    ux = (round(min(u0, u1)), round(max(u0, u1)))
    vy = (round(min(v0, v1)), round(max(v0, v1)))
    x_rng, y_rng = (vy, ux) if swap else (ux, vy)
    return {"x_min": x_rng[0], "x_max": x_rng[1], "y_min": y_rng[0], "y_max": y_rng[1],
            "swap_xy": swap, "invert_x": u1 < u0, "invert_y": v1 < v0}


class TouchWizard:
    """Stato della calibrazione in corso: croce da toccare, punti raccolti, scadenza."""

    def __init__(self, rotate: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.rotate = rotate
        self._clock = clock
        self.raws: list[tuple[int, int]] = []
        self._last = clock()

    @property
    def step(self) -> int:
        return len(self.raws)

    def target(self) -> tuple[float, float] | None:
        """Croce da toccare ora (coordinate del fotogramma), None a fine giro."""
        return TARGETS[self.step] if self.step < len(TARGETS) else None

    def expired(self) -> bool:
        return self._clock() - self._last > TIMEOUT_S

    def add(self, tap: Tap) -> bool:
        """Registra un tocco; True quando le quattro croci sono state toccate."""
        # senza valori grezzi (simulatore) si usano le coordinate come un controller a 12 bit
        raw = tap.raw or (round(tap.x * 4095), round(tap.y * 4095))
        self.raws.append(raw)
        self._last = self._clock()
        return self.step >= len(TARGETS)

    def result(self) -> dict[str, Any] | None:
        if self.step < len(TARGETS):
            return None
        return solve([frame_to_panel(x, y, self.rotate) for x, y in TARGETS], self.raws)
