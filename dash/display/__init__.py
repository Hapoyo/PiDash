"""Uscite video: simulatore (PNG + pagina web) e framebuffer Linux (schermo SPI 3,5")."""
from __future__ import annotations

from typing import Any, Callable

from .base import Display


def make_display(cfg: dict[str, Any], on_key: Callable[[str], None] | None = None,
                 on_tap: Callable[[float, float], None] | None = None) -> Display:
    """Crea il display indicato da `display.driver`."""
    d = cfg["display"]
    driver = d["driver"]
    if driver == "sim":
        from .sim import SimDisplay
        return SimDisplay(d["width"], d["height"], cfg["sim"], on_key, rotate=d["rotate"],
                          on_tap=on_tap)
    if driver == "fb":
        from .fb import FramebufferDisplay
        fbd = FramebufferDisplay(d["width"], d["height"], cfg["fb"])
        # width/height = pannello; con rotate 90/270 l'app disegna in verticale e ruota.
        d["width"], d["height"] = fbd.width, fbd.height
        return fbd
    raise ValueError(f"display.driver sconosciuto: {driver!r} (validi: sim, fb)")


__all__ = ["Display", "make_display"]
