"""Luminosità dello schermo: retroilluminazione vera se il pannello la espone, altrimenti software.

Molti schermi SPI da 3,5" hanno il LED collegato fisso o solo acceso/spento: in quel caso si
scurisce l'immagine prima di mandarla al pannello (il LED resta acceso, ma lo schermo è più
tenue di notte).

Modi (`backlight.mode`): "auto" (hardware se regolabile, altrimenti software), "hw", "sw".
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PIL import Image

log = logging.getLogger(__name__)

SYS_BACKLIGHT = Path("/sys/class/backlight")
MODES = ("auto", "hw", "sw")
LEVEL_MIN, LEVEL_MAX, LEVEL_STEP = 10, 100, 10


def clamp(level: float) -> int:
    return int(max(LEVEL_MIN, min(LEVEL_MAX, round(level))))


class Backlight:
    """Livello 10…100 %; `apply` scurisce il fotogramma quando serve il ripiego software."""

    def __init__(self, level: int = 100, mode: str = "auto", sys_dir: Path = SYS_BACKLIGHT) -> None:
        if mode not in MODES:
            raise ValueError(f"backlight.mode deve essere uno di {MODES}")
        self.mode = mode
        self.level = clamp(level)
        self._dev: Path | None = None
        self._max = 0
        if mode != "sw":
            self._dev, self._max = self._find(sys_dir)
        self._lut: list[int] = []
        self._lut_level = -1
        self.set(self.level)

    @classmethod
    def from_cfg(cls, cfg: dict[str, Any], sys_dir: Path = SYS_BACKLIGHT) -> Backlight:
        return cls(int(cfg.get("level", 100)), str(cfg.get("mode", "auto")), sys_dir)

    @staticmethod
    def _find(sys_dir: Path) -> tuple[Path | None, int]:
        """Primo dispositivo in /sys/class/backlight con il suo massimo."""
        try:
            devs = sorted(p for p in sys_dir.iterdir() if (p / "brightness").exists())
        except OSError:
            return None, 0
        for dev in devs:
            try:
                return dev, int((dev / "max_brightness").read_text().strip())
            except (OSError, ValueError):
                continue
        return None, 0

    @property
    def hardware(self) -> bool:
        """True se il LED si regola davvero (non solo acceso/spento)."""
        return self._dev is not None and self._max > 1

    @property
    def software(self) -> bool:
        return not self.hardware

    def set(self, level: float) -> int:
        """Nuovo livello (limitato a 10…100); scrive la retroilluminazione se regolabile."""
        self.level = clamp(level)
        if self._dev is None:
            return self.level
        value = round(self._max * self.level / 100) if self.hardware else 1  # on/off: sempre acceso
        try:
            (self._dev / "brightness").write_text(f"{value}\n")
        except OSError as exc:
            log.warning("retroilluminazione %s non scrivibile (%s): uso il ripiego software",
                        self._dev, exc)
            self._dev, self._max = None, 0
        return self.level

    def step(self, delta: int) -> int:
        return self.set(self.level + delta)

    def apply(self, img: Image.Image) -> Image.Image:
        """Fotogramma da mandare al pannello: scurito solo nel modo software sotto il 100 %."""
        if self.hardware or self.level >= LEVEL_MAX:
            return img
        if self._lut_level != self.level:  # tabella per i tre canali, ricalcolata solo al cambio
            f = self.level / 100
            self._lut = [round(i * f) for i in range(256)] * 3
            self._lut_level = self.level
        return img.point(self._lut)
