"""Geometria e nomi dei giorni/mesi condivisi dalle pagine."""
from __future__ import annotations

from dataclasses import dataclass

GIORNI = ("LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM")
MESI = ("GEN", "FEB", "MAR", "APR", "MAG", "GIU", "LUG", "AGO", "SET", "OTT", "NOV", "DIC")


@dataclass(frozen=True)
class Box:
    """Rettangolo in pixel: (x, y) angolo in alto a sinistra, w×h dimensioni."""
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    @property
    def rect(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.right - 1, self.bottom - 1

    def inset(self, dx: int, dy: int | None = None) -> Box:
        dy = dx if dy is None else dy
        return Box(self.x + dx, self.y + dy, max(0, self.w - 2 * dx), max(0, self.h - 2 * dy))
