"""Superficie di disegno di un fotogramma: primitive dello stile e registro delle animazioni.

Le pagine disegnano solo attraverso `Canvas`: colori per nome, misure dalla griglia (`GRID`,
già scalate: `cv.gap`, `cv.pad`, `cv.radius`…), testi dalla cache, pannelli, anelli, barre,
righe, grafici. Durante il disegno il Canvas registra i numeri che possono decodificarsi
(`slots`) e gli effetti continui (`fx`), che `compose` anima sopra la pagina.
"""
from __future__ import annotations

import math
from typing import Any

from PIL import Image, ImageDraw

from ..layout import Box
from ..motion import Fx, Slot
from .theme import GRID, fit, font, px, text_mask

Color = str | tuple[int, int, int]


class Canvas:
    """Immagine RGB + colori del tema + scala `u` (1 = schermo 480×320)."""

    def __init__(self, img: Image.Image, colors: dict[str, tuple[int, int, int]], u: float) -> None:
        self.img = img
        self.d = ImageDraw.Draw(img)
        self.c = colors
        self.u = u
        self.slots: list[Slot] = []
        self.fx: list[Fx] = []
        # misure della griglia alla scala di questo schermo
        self.margin, self.gap, self.pad = self.px(GRID.margin), self.px(GRID.gap), self.px(GRID.pad)
        self.radius, self.line, self.stroke = self.px(GRID.radius), self.px(GRID.line), self.px(GRID.stroke)
        self.f_label = font("mono", self.px(GRID.label))
        self.f_bold = font("mono", self.px(GRID.label), 700)
        self.f_small = font("mono", self.px(GRID.small))

    def px(self, n: float) -> int:
        """Misura della griglia (pixel a 480×320) alla scala dello schermo, almeno 1."""
        return px(n, self.u)

    @staticmethod
    def height(f: Any) -> int:
        """Spazio verticale di una riga ancorata in alto ("la"): dall'ancora al fondo delle gambe."""
        return f.getbbox("Hgjà", anchor="la")[3]

    # --- colori ------------------------------------------------------------
    def rgb(self, c: Color) -> tuple[int, int, int]:
        return self.c[c] if isinstance(c, str) else c

    def mix(self, a: str, b: str, f: float) -> tuple[int, int, int]:
        """Colore fra `a` (f=0) e `b` (f=1): dissolvenze senza canale alfa."""
        ca, cb = self.c[a], self.c[b]
        f = max(0.0, min(1.0, f))
        return tuple(round(x + (y - x) * f) for x, y in zip(ca, cb))  # type: ignore[return-value]

    # --- forme -------------------------------------------------------------
    def rect(self, box: Box | tuple[float, float, float, float], fill: Color | None,
             outline: Color | None = None, width: int | None = None, r: int | None = None) -> None:
        """Rettangolo arrotondato (raggio della griglia se `r` manca); `box` Box o (x0, y0, x1, y1)."""
        xy = box.rect if isinstance(box, Box) else box
        self.d.rounded_rectangle(xy, radius=self.radius if r is None else r,
                                 fill=None if fill is None else self.rgb(fill),
                                 outline=None if outline is None else self.rgb(outline),
                                 width=self.line if width is None else width)

    def progress(self, bar: Box, frac: float, color: str, track: str = "line",
                 outline: str | None = None, show_empty: bool = True) -> None:
        """Barra arrotondata: fondo `track`, parte piena `color` proporzionale a `frac`."""
        self.rect(bar, track, outline, r=bar.h // 2)
        if frac > 0 or show_empty:
            self.rect((bar.x, bar.y, bar.x + max(bar.h, round(bar.w * min(1.0, frac))), bar.bottom - 1),
                      color, r=bar.h // 2)

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

    def label(self, xy: tuple[float, float], s: str, fill: Color = "cream", anchor: str = "la",
              small: bool = False, bold: bool = False, lower: bool = True) -> None:
        """Etichetta in Space Mono ai due corpi della griglia; `lower=False` per kB/s, °C."""
        f = self.f_small if small else (self.f_bold if bold else self.f_label)
        self.text(xy, s.lower() if lower else s, f, fill, anchor)

    def big(self, box: Box, s: str, fill: str, weight: int = 500, anchor: str = "ls",
            pos: tuple[float, float] | None = None, slot: str | None = None, bg: str = "panel",
            live: bool = False, ref: str | None = None) -> Any:
        """Numero grande adattato al riquadro (taglia da `ref`, se c'è); `slot` lo registra."""
        f = fit(ref or s, "grotesk", weight, box.w, box.h)
        x, y = pos if pos else (box.x, box.bottom)
        self.text((x, y), s, f, fill, anchor)
        if slot:
            self.slot(slot, s, (x, y), anchor, f, fill, bg, live)
        return f

    # --- componenti ricorrenti -----------------------------------------------
    def panel(self, box: Box, fill: str, label: str, value: str, foot: str = "",
              ref: str | None = None, reserve: int = 0, slot: str | None = None,
              live: bool = False) -> None:
        """Pannello a colori: etichetta, numero grande e dettaglio, tutti allineati a sinistra.

        Se il pannello è basso il numero va a destra dell'etichetta, sulla stessa riga.
        `ref` dà la taglia del numero (serie allineate: 7% e 100% uguali); `reserve` lascia
        libera quella larghezza a destra, per tutta l'altezza (anello del vento).
        """
        self.rect(box, fill)
        pad = self.pad
        lab_h = self.height(self.f_label)
        if box.h < 2 * pad + 2 * lab_h + self.gap:  # riga unica: etichetta … numero
            self.label((box.x + pad, box.y + box.h / 2), label, "ink", "lm")
            room = box.w - 2 * pad - round(self.f_label.getlength(label.lower())) - self.gap
            num = Box(box.right - pad - room, box.y + pad // 2, room, box.h - pad)
            self.big(num, value, "ink", anchor="rs", pos=(box.right - pad, num.bottom), ref=ref,
                     slot=slot, bg=fill, live=live)
            return
        self.label((box.x + pad, box.y + pad), label, "ink")
        foot_h = self.height(self.f_small) + self.gap if foot else 0
        top = box.y + pad + lab_h + self.gap
        num = Box(box.x + pad, top, box.w - 2 * pad - reserve, box.bottom - pad - foot_h - top)
        if num.h > self.px(10):
            self.big(num, value, "ink", ref=ref, slot=slot, bg=fill, live=live)
        if foot:
            self.label((box.x + pad, box.bottom - pad), foot, "ink", "ld", small=True)

    def row_step(self) -> int:
        """Passo verticale fra righe di etichette."""
        return self.height(self.f_label) + self.px(3)

    def rows(self, box: Box, rows: list[tuple[str, str]], key_color: str = "tan",
             lower: bool = True, value_x: int | None = None) -> None:
        """Righe "etichetta … valore" a passo fisso dall'alto (quelle che ci stanno).

        Valori allineati a destra del riquadro, oppure a sinistra a `value_x` dal bordo
        (colonne affiancate: i valori non toccano la colonna vicina).
        """
        step = self.row_step()
        n = max(0, min(len(rows), (box.h + self.px(3)) // step))
        col = "cream" if key_color == "tan" else "tan"
        for i, (k, v) in enumerate(rows[:n]):
            y = box.y + i * step
            self.label((box.x, y), k, key_color)
            if value_x is None:
                self.label((box.right, y), str(v), col, "ra", lower=lower)
            else:
                self.label((box.x + value_x, y), str(v), col, "la", lower=lower)

    def graph(self, box: Box, vals: list[float], top: float, label: str, color: str) -> None:
        """Istogramma a colonne di larghezza fissa: lo storico cresce da sinistra."""
        pad = self.pad
        self.rect(box, "panel", "line")
        self.label((box.x + pad, box.y + pad - self.px(2)), label, "tan", small=True, lower=False)
        head = self.height(self.f_small) + self.gap
        inner = Box(box.x + pad, box.y + pad + head, box.w - 2 * pad, box.h - 2 * pad - head)
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
        pad = self.px(2)
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
