"""Superficie di disegno di un fotogramma: primitive dello stile e registro delle animazioni.

Le pagine disegnano solo attraverso `Canvas`: colori per nome, testi dalla cache, pannelli,
anelli, barre, righe, grafici. Durante il disegno il Canvas registra i numeri che possono
decodificarsi (`slots`) e gli effetti continui (`fx`), che `compose` anima sopra la pagina.
"""
from __future__ import annotations

import math
from typing import Any

from PIL import Image, ImageDraw

from ..layout import Box
from ..motion import Fx, Slot
from .theme import fit, font, text_mask

Color = str | tuple[int, int, int]


class Canvas:
    """Immagine RGB + colori del tema + scala `u` (1 = riferimento 960×540)."""

    def __init__(self, img: Image.Image, colors: dict[str, tuple[int, int, int]], u: float) -> None:
        self.img = img
        self.d = ImageDraw.Draw(img)
        self.c = colors
        self.u = u
        self.slots: list[Slot] = []
        self.fx: list[Fx] = []

    # --- colori ------------------------------------------------------------
    def rgb(self, c: Color) -> tuple[int, int, int]:
        return self.c[c] if isinstance(c, str) else c

    def mix(self, a: str, b: str, f: float) -> tuple[int, int, int]:
        """Colore fra `a` (f=0) e `b` (f=1): dissolvenze senza canale alfa."""
        ca, cb = self.c[a], self.c[b]
        f = max(0.0, min(1.0, f))
        return tuple(round(x + (y - x) * f) for x, y in zip(ca, cb))  # type: ignore[return-value]

    # --- forme -------------------------------------------------------------
    def rect(self, box: Box | tuple[float, float, float, float], r: int, fill: Color | None,
             outline: Color | None = None, width: int = 1) -> None:
        """Rettangolo arrotondato; `box` come Box o come (x0, y0, x1, y1) inclusivo."""
        xy = box.rect if isinstance(box, Box) else box
        self.d.rounded_rectangle(xy, radius=r, fill=None if fill is None else self.rgb(fill),
                                 outline=None if outline is None else self.rgb(outline), width=width)

    def progress(self, bar: Box, frac: float, color: str, track: str = "line",
                 outline: str | None = None, width: int = 1, show_empty: bool = True) -> None:
        """Barra arrotondata: fondo `track`, parte piena `color` proporzionale a `frac`."""
        self.rect(bar, bar.h // 2, track, outline, width)
        if frac > 0 or show_empty:
            self.rect((bar.x, bar.y, bar.x + max(bar.h, round(bar.w * frac)), bar.bottom - 1),
                      bar.h // 2, color)

    def ring(self, box: Box, frac: float, color: str, lw: int, dot: float,
             track: Color = "line", bg: str = "panel") -> None:
        """Anello spento + arco acceso da ore 12 in senso orario, con una sfera in testa."""
        self.d.ellipse(box.rect, outline=self.rgb(track), width=lw)
        ang = -90 + 360 * max(0.0, min(1.0, frac))
        if frac > 0:
            self.d.arc(box.rect, -90, ang, fill=self.c[color], width=lw)
        cx, cy = box.x + box.w / 2, box.y + box.h / 2
        rad = math.radians(ang)
        px, py = cx + (box.w / 2) * math.cos(rad), cy + (box.h / 2) * math.sin(rad)
        self.d.ellipse((px - dot, py - dot, px + dot, py + dot), fill=self.c[color])
        self.add_fx("pulse", (px - dot, py - dot, px + dot, py + dot), color, bg, phase=frac)

    # --- testo -------------------------------------------------------------
    def text(self, xy: tuple[float, float], s: str, f: Any, fill: Color, anchor: str = "la") -> None:
        mask, dx, dy = text_mask(s, f, anchor)
        self.d.bitmap((round(xy[0]) + dx, round(xy[1]) + dy), mask, fill=self.rgb(fill))

    def micro(self, xy: tuple[float, float], s: str, fill: Color = "cream", anchor: str = "la",
              size: float = 11, lower: bool = True) -> None:
        """Microetichetta in Space Mono; `lower=False` dove il maiuscolo conta (kB/s, °C)."""
        self.text(xy, s.lower() if lower else s, font("mono", round(size * self.u)), fill, anchor)

    def big(self, box: Box, s: str, fill: str, weight: int = 500, anchor: str = "ls",
            pos: tuple[float, float] | None = None, slot: str | None = None, bg: str = "panel",
            live: bool = False) -> Any:
        """Numero grande adattato al riquadro; `slot` lo registra per la decodifica."""
        f = fit(s, "grotesk", weight, box.w, box.h)
        x, y = pos if pos else (box.x, box.bottom)
        self.text((x, y), s, f, fill, anchor)
        if slot:
            self.slot(slot, s, (x, y), anchor, f, fill, bg, live)
        return f

    # --- componenti ricorrenti -----------------------------------------------
    def panel(self, box: Box, fill: str, label: str, value: str, foot: str, r: int,
              ref: str | None = None, reserve: int = 0, slot: str | None = None,
              live: bool = False) -> None:
        """Pannello con etichetta in alto, numero grande al centro e riga di dettaglio in basso.

        `ref` dà la taglia del numero (serie allineate: 7% e 100% uguali); `reserve` lascia
        libera quella larghezza a destra del numero (anello del vento).
        """
        u = self.u
        self.rect(box, r, fill)
        pad = max(4, round(11 * u))
        lab = font("mono", round(11 * u))
        lab_h = int(lab.size) + max(2, round(3 * u))
        self.text((box.x + pad, box.y + pad), label.lower(), lab, "ink", "la")
        foot_h = (lab_h + max(2, round(3 * u))) if foot else 0
        big = Box(box.x + pad, box.y + pad + lab_h, box.w - 2 * pad - reserve,
                  box.h - 2 * pad - lab_h - foot_h)
        if big.h > round(10 * u):
            f = fit(ref or value, "grotesk", 500, big.w, big.h)
            self.text((big.x, big.bottom), value, f, "ink", "ls")
            if slot:
                self.slot(slot, value, (big.x, big.bottom), "ls", f, "ink", fill, live)
        if foot:
            self.text((box.right - pad, box.bottom - pad), foot.lower(), lab, "ink", "rd")

    def rows(self, box: Box, rows: list[tuple[str, str]], key_color: str = "tan",
             lower: bool = True) -> None:
        """Righe "etichetta … valore" distribuite nello spazio disponibile (quelle che ci stanno)."""
        u = self.u
        line_h = max(round(15 * u), round(12 * u) + round(6 * u))
        n = max(1, min(len(rows), box.h // line_h))
        step = box.h / n
        for i, (k, v) in enumerate(rows[:n]):
            y = box.y + i * step + (step - round(12 * u)) / 2
            self.micro((box.x, y), k, key_color, "la", 12)
            self.micro((box.right, y), str(v), "cream" if key_color == "tan" else "tan", "ra", 12,
                       lower=lower)

    def graph(self, box: Box, vals: list[float], top: float, label: str, color: str, r: int,
              pad: int) -> None:
        """Istogramma a colonne di larghezza fissa: lo storico cresce da sinistra."""
        u = self.u
        self.rect(box, r, "panel", "line", max(1, round(2 * u)))
        self.micro((box.x + pad, box.y + round(6 * u)), label, "tan", "la", 11, lower=False)
        inner = box.inset(pad, round(20 * u))
        slots = 48
        vals = vals[-slots:]
        if not vals or top <= 0 or inner.w <= 0 or inner.h <= 0:
            return
        bw = inner.w / slots
        for i, v in enumerate(vals):
            hgt = max(1, round(inner.h * max(0.0, min(1.0, v / top))))
            x = inner.x + i * bw
            self.d.rectangle((x, inner.bottom - hgt, x + max(1, bw - 1), inner.bottom - 1),
                             fill=self.c[color])

    # --- registro per le animazioni ---------------------------------------
    def slot(self, key: str, text: str, xy: tuple[float, float], anchor: str, f: Any,
             fill: str, bg: str, live: bool = False) -> None:
        """Numero che può decodificarsi; `live`: solo all'apertura della pagina (cambia spesso)."""
        if len(anchor) < 2 or anchor[1] != "s":
            return  # la decodifica posiziona le cifre sulla linea di base
        left, top, right, bottom = f.getbbox(text, anchor=anchor)
        pad = 3
        box = (round(xy[0] + left) - pad, round(xy[1] + top) - pad,
               round(xy[0] + right) + pad, round(xy[1] + bottom) + pad)
        self.slots.append(Slot(key, text, xy, anchor, f, fill, bg, box, live))

    def add_fx(self, kind: str, box: tuple[float, float, float, float], color: str = "cream",
               bg: str = "panel", phase: float = 0.0, extra: tuple[float, ...] = ()) -> None:
        self.fx.append(Fx(kind, tuple(round(v) for v in box), color, bg, phase, extra))  # type: ignore[arg-type]

    @staticmethod
    def left(s: str, f: Any, x: float, anchor: str) -> float:
        """Bordo sinistro della riga di testo per ancoraggi l/m/r."""
        total = f.getlength(s)
        return x - total / 2 if anchor[0] == "m" else (x - total if anchor[0] == "r" else x)

    def colon_fx(self, s: str, f: Any, xy: tuple[float, float], anchor: str, bg: str) -> None:
        """Due punti dell'ora che lampeggiano (solo ancoraggi sulla linea di base)."""
        if ":" not in s or len(anchor) < 2 or anchor[1] != "s":
            return
        x0 = self.left(s, f, xy[0], anchor) + f.getlength(s[:s.index(":")])
        left, top, right, bottom = f.getbbox(":", anchor="ls")
        self.add_fx("blink", (x0 + left - 1, xy[1] + top - 1, x0 + right + 1, xy[1] + bottom + 1),
                    bg=bg)
