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
_GRADIENTS: dict[tuple, tuple[Image.Image, Image.Image]] = {}  # sfumature dei pannelli già pronte


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

    def solid(self, box: Box | tuple[float, float, float, float], fill: str, r: int | None = None,
              depth: bool = True) -> None:
        """Pannello a rilievo: ombra morbida sotto, sfumatura leggera dall'alto, filo di luce.

        Stesso ingombro di `rect`: l'ombra cade nello spazio fra pannelli (`gap`). Con `depth`
        falso (cartelle, linguette) disegna solo la sfumatura e il filo di luce.
        """
        xy = tuple(round(v) for v in (box.rect if isinstance(box, Box) else box))
        r = self.radius if r is None else r
        w, h = xy[2] - xy[0], xy[3] - xy[1]
        if w < 4 or h < 4:
            self.rect(xy, fill, r=r)
            return
        if depth:
            dy = self.px(2)
            self.d.rounded_rectangle((xy[0], xy[1] + dy, xy[2], xy[3] + dy), radius=r,
                                     fill=self.mix(fill, "bg", 0.62))
        top, bottom = self.mix(fill, "paper", 0.12), self.mix(fill, "ink", 0.10)
        key = (w + 1, h + 1, r, top, bottom)
        body = _GRADIENTS.get(key)
        if body is None:
            strip = Image.new("RGB", (1, h + 1))
            for y in range(h + 1):
                f = y / max(1, h)
                strip.putpixel((0, y), tuple(round(a + (b - a) * f) for a, b in zip(top, bottom)))
            mask = Image.new("L", (w + 1, h + 1))
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=r, fill=255)
            body = _GRADIENTS[key] = (strip.resize((w + 1, h + 1)), mask)
            if len(_GRADIENTS) > 64:
                _GRADIENTS.pop(next(iter(_GRADIENTS)))
        self.img.paste(body[0], (xy[0], xy[1]), body[1])
        light = self.mix(fill, "paper", 0.42)
        self.d.line((xy[0] + r, xy[1] + 1, xy[2] - r, xy[1] + 1), fill=light, width=1)

    def key(self, box: Box, fill: str, outline: Color | None, width: int | None = None) -> None:
        """Bottone in rilievo: sfumatura, contorno e un'ombra sottile lungo il bordo basso."""
        self.solid(box, fill, depth=False)
        self.rect(box, None, outline, width)
        r, y = self.radius, round(box.y + box.h) - 2
        self.d.line((round(box.x) + r, y, round(box.x + box.w) - r, y),
                    fill=self.mix(fill, "ink", 0.45), width=1)

    def icon(self, kind: str, box: Box, color: Color, bg: Color) -> None:
        """Icona meteo a linee piene (sole, nuvola, pioggia, neve, temporale, nebbia) in `box`."""
        s = min(box.w, box.h)
        cx, cy = box.x + box.w / 2, box.y + box.h / 2
        col, d = self.rgb(color), self.d
        lw = max(1, round(s / 14))

        def sun(x: float, y: float, r: float) -> None:
            for i in range(8):
                a = i * math.pi / 4
                d.line((x + math.cos(a) * r * 1.45, y + math.sin(a) * r * 1.45,
                        x + math.cos(a) * r * 1.95, y + math.sin(a) * r * 1.95), fill=col, width=lw)
            d.ellipse((x - r, y - r, x + r, y + r), fill=col)

        def cloud(x: float, y: float, w: float) -> None:
            h = w * 0.34
            d.ellipse((x - w * .5, y - h * .2, x - w * .1, y + h * .6), fill=col)
            d.ellipse((x - w * .28, y - h * .9, x + w * .18, y + h * .6), fill=col)
            d.ellipse((x - w * .02, y - h * .5, x + w * .5, y + h * .6), fill=col)
            d.rectangle((x - w * .3, y, x + w * .3, y + h * .6), fill=col)

        if kind == "sun":
            sun(cx, cy, s * 0.22)
        elif kind == "partly":
            sun(cx + s * .12, cy - s * .14, s * .16)
            cloud(cx - s * .04, cy + s * .12, s * .8)
        elif kind == "fog":
            for i in range(4):
                y = cy - s * .27 + i * s * .18
                d.line((cx - s * .4 + (i % 2) * s * .1, y, cx + s * .4 - (i % 2) * s * .1, y),
                       fill=col, width=lw)
        else:
            cloud(cx, cy - s * .12, s * .86)
            for i in range(3):
                x, y = cx - s * .25 + i * s * .25, cy + s * .3
                if kind == "snow":
                    d.ellipse((x - lw, y - lw, x + lw, y + lw), fill=col)
                elif kind == "storm" and i == 1:
                    d.polygon([(x + lw, y - s * .1), (x - lw * 1.5, y + s * .06), (x, y + s * .06),
                               (x - lw, y + s * .22), (x + lw * 1.8, y + s * .02), (x + lw * .3, y + s * .02)],
                              fill=self.rgb("amber"))
                elif kind != "cloud":
                    d.line((x + lw, y - s * .06, x - lw, y + s * .14), fill=col, width=lw)

    def qr(self, box: Box, moduli: list[list[bool]], dark: Color = "ink",
           light: Color = "cream") -> None:
        """QR code centrato in `box`: moduli interi di pixel, su fondo `light` con due moduli di
        margine (il bianco attorno serve alla fotocamera); niente se non ci sta a 2 px per modulo."""
        n = len(moduli)
        lato = min(box.w, box.h) // (n + 4)
        if lato < 2:
            return
        tot = lato * (n + 4)
        x0, y0 = box.x + (box.w - tot) // 2, box.y + (box.h - tot) // 2
        self.d.rectangle((x0, y0, x0 + tot - 1, y0 + tot - 1), fill=self.rgb(light))
        x0, y0 = x0 + 2 * lato, y0 + 2 * lato
        scuro = self.rgb(dark)
        for y, riga in enumerate(moduli):
            for x, pieno in enumerate(riga):
                if pieno:
                    self.d.rectangle((x0 + x * lato, y0 + y * lato, x0 + (x + 1) * lato - 1,
                                      y0 + (y + 1) * lato - 1), fill=scuro)

    def progress(self, bar: Box, frac: float, color: str, track: str = "line",
                 outline: str | None = None, show_empty: bool = True) -> None:
        """Barra arrotondata: fondo `track`, parte piena `color` proporzionale a `frac`."""
        self.rect(bar, track, outline, r=bar.h // 2)
        if frac > 0 or show_empty:
            end = bar.x + max(bar.h, round(bar.w * min(1.0, frac)))
            self.rect((bar.x, bar.y, end, bar.bottom - 1), color, r=bar.h // 2)
            if bar.h >= 5:  # riflesso sul bordo alto della parte piena
                self.d.line((bar.x + bar.h // 2, bar.y + 1, end - bar.h // 2, bar.y + 1),
                            fill=self.mix(color, "paper", 0.45), width=1)

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

    def gear(self, center: tuple[float, float], r: float, color: Color, bg: Color,
             teeth: int = 8) -> None:
        """Ingranaggio (linguetta delle Impostazioni): corona dentata con il foro al centro."""
        cx, cy = center
        inner, step = r * 0.74, 2 * math.pi / teeth
        pts: list[tuple[float, float]] = []
        for i in range(teeth):  # dente da -0,2 a +0,2 del passo, gola da 0,3 a 0,7
            for da, rr in ((-0.2, r), (0.2, r), (0.3, inner), (0.7, inner)):
                a = (i + da) * step - math.pi / 2
                pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        self.d.polygon(pts, fill=self.rgb(color))
        hole = r * 0.34
        self.d.ellipse((cx - hole, cy - hole, cx + hole, cy + hole), fill=self.rgb(bg))

    def power(self, center: tuple[float, float], r: float, color: Color, width: int) -> None:
        """Simbolo di accensione: cerchio aperto in alto con la barra verticale."""
        cx, cy = center
        self.d.arc((cx - r, cy - r, cx + r, cy + r), -60, 240, fill=self.rgb(color), width=width)
        self.d.line((cx, cy - r - width / 2, cx, cy), fill=self.rgb(color), width=width)

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
        self.solid(box, fill)
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
