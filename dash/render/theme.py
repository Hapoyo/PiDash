"""Tema "cyber": colori, font e cache dei testi già rasterizzati.

Computer di bordo retro futuristico: fondo quasi nero, pannelli arrotondati pieni (arancio, ambra,
crema, grigio caldo, rosa), numeri grandi in Space Grotesk, microetichette in Space Mono.
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)

PALETTE: dict[str, str] = {
    "bg": "#1d1815",       # fondo
    "panel": "#2a2320",    # pannello scuro
    "cream": "#eee4cd",    # linguette chiuse, testo chiaro
    "paper": "#f6efdf",    # crema più chiaro (testo del riquadro di allarme)
    "tan": "#a59b8c",
    "orange": "#ee7b50",
    "amber": "#f2bb5b",
    "pink": "#e8505b",
    "ink": "#1d1815",      # testo scuro
    "line": "#5b514a",     # linee sottili e anelli spenti
}

FONT_DIR = Path(__file__).resolve().parents[2] / "fonts"
_FONTS: dict[tuple[str, int, int], ImageFont.FreeTypeFont] = {}


def font(kind: str, size: int, weight: int = 500) -> ImageFont.FreeTypeFont:
    """kind: "grotesk" (variabile 300–700) o "mono" (Space Mono regular/bold)."""
    size = max(8 if kind == "mono" else 6, int(size))  # microetichette leggibili anche a 480×320
    key = (kind, size, weight)
    if key not in _FONTS:
        try:
            if kind == "grotesk":
                f = ImageFont.truetype(str(FONT_DIR / "SpaceGrotesk.ttf"), size)
                try:
                    f.set_variation_by_axes([max(300, min(700, weight))])
                except (OSError, ValueError):
                    pass
            else:
                name = "SpaceMono-Bold.ttf" if weight >= 600 else "SpaceMono-Regular.ttf"
                f = ImageFont.truetype(str(FONT_DIR / name), size)
        except OSError:
            log.warning("font %s non trovato, uso quello di Pillow", kind)
            f = ImageFont.load_default(size)  # type: ignore[assignment]
        _FONTS[key] = f
    return _FONTS[key]


def fit(s: str, kind: str, weight: int, max_w: float, max_h: float) -> ImageFont.FreeTypeFont:
    """Font più grande con cui `s` sta in max_w × max_h."""
    lo, hi = 6, max(6, int(max_h * 1.4))
    while lo < hi:
        mid = (lo + hi + 1) // 2
        left, top, right, bottom = font(kind, mid, weight).getbbox(s, anchor="ls")
        if right - left <= max_w and bottom - top <= max_h:
            lo = mid
        else:
            hi = mid - 1
    return font(kind, lo, weight)


_MASKS: OrderedDict[tuple[str, int, str], tuple[Image.Image, int, int]] = OrderedDict()
MASK_CACHE = 1024  # testi già rasterizzati: FreeType è l'88% del tempo di disegno


def text_mask(s: str, f: Any, anchor: str) -> tuple[Image.Image, int, int]:
    """Maschera "L" del testo e scostamento dal punto di ancoraggio; in cache (LRU)."""
    key = (s, id(f), anchor)  # i font restano in _FONTS per tutta la vita del programma
    hit = _MASKS.get(key)
    if hit is not None:
        _MASKS.move_to_end(key)
        return hit
    left, top, right, bottom = f.getbbox(s, anchor=anchor)
    mask = Image.new("L", (max(1, right - left), max(1, bottom - top)))
    ImageDraw.Draw(mask).text((-left, -top), s, font=f, fill=255, anchor=anchor)
    _MASKS[key] = (mask, left, top)
    if len(_MASKS) > MASK_CACHE:
        _MASKS.popitem(last=False)
    return mask, left, top
