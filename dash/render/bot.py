"""Bot di Needle: una testa di robot che mostra cosa sta facendo il modello.

Una sola funzione, `draw`, disegna il bot per un istante `t`: la pagina base lo disegna fermo
(`t = 0`, occhi aperti), l'effetto "bot" (`effects.draw_fx`) lo ridisegna a ogni fotogramma sopra
la base. La geometria è in frazioni del lato del riquadro, quindi vale a ogni risoluzione.

Facce (`MOODS`, le stesse di `NeedleWidget.umore`):
- offline:   occhi chiusi, antenna spenta, "z" che salgono;
- controllo: occhi che guardano a destra e a sinistra;
- pronto:    occhi aperti che ogni tanto sbattono, antenna che pulsa;
- penso:     occhi in alto, tre puntini che si accendono uno dopo l'altro, antenna che lampeggia;
- fatto:     occhi sorridenti "^ ^", bocca sorridente, saltello;
- dubbio:    un occhio più grande, sopracciglio storto, bocca storta, punto interrogativo;
- errore:    occhi a croce rosa, bocca a zig-zag, la testa scuote ogni tanto.
"""
from __future__ import annotations

import math

from ..layout import Box
from ..motion import wave
from .canvas import Canvas
from .theme import font

MOODS = ("offline", "controllo", "pronto", "penso", "fatto", "dubbio", "errore")

# geometria, in frazioni del lato `s` del riquadro (origine in alto a sinistra)
TESTA = (0.06, 0.24, 0.94, 0.94)
TESTA_R = 0.18
ORECCHIE = ((0.0, 0.48, 0.06, 0.70), (0.94, 0.48, 1.0, 0.70))
ANTENNA = (0.5, 0.24, 0.5, 0.10)       # dal bordo della testa alla pallina
PALLINA_R = 0.065
OCCHI_X = (0.32, 0.68)
OCCHI_Y = 0.52
OCCHIO_W, OCCHIO_H = 0.085, 0.10       # mezza larghezza e mezza altezza
BOCCA_Y = 0.79
SBATTE_S, SBATTE_DUR = 3.6, 0.16       # ogni quanti secondi sbatte le palpebre e per quanto
SCUOTE_S, SCUOTE_DUR = 3.0, 0.8        # ogni quanti secondi scuote la testa (errore)


def _occhi(cv: Canvas, s: float, x0: float, y0: float, umore: str, t: float, colore: str) -> None:
    """Gli occhi della faccia `umore`; centro (x0, y0) del riquadro, lato `s`."""
    d, w = cv.d, cv.stroke
    ew, eh = OCCHIO_W * s, OCCHIO_H * s
    sbatte = (t % SBATTE_S) > SBATTE_S - SBATTE_DUR
    for k, ex in enumerate(OCCHI_X):
        cx, cy = x0 + ex * s, y0 + OCCHI_Y * s
        if umore == "offline":                       # chiusi
            d.line((cx - ew, cy, cx + ew, cy), fill=cv.c[colore], width=w)
        elif umore == "fatto":                       # ^ ^
            d.arc((cx - ew, cy - eh * 0.5, cx + ew, cy + eh * 1.5), 200, 340, fill=cv.c[colore],
                  width=w + 1)
        elif umore == "errore":                      # x x
            r = ew * 0.8
            d.line((cx - r, cy - r, cx + r, cy + r), fill=cv.c[colore], width=w + 1)
            d.line((cx - r, cy + r, cx + r, cy - r), fill=cv.c[colore], width=w + 1)
        else:
            gx, gy, h = 0.0, 0.0, eh
            if umore == "controllo":                 # occhi stretti che guardano a destra e a sinistra
                gx, h = math.sin(t * 3.0) * 0.05 * s, eh * 0.7
            elif umore == "penso":                   # guarda in alto a destra
                gx, gy = 0.035 * s, -0.045 * s
            elif umore == "dubbio" and k == 1:       # un occhio più grande e il sopracciglio
                h = eh * 1.35
                d.line((cx - ew, cy - h - 0.05 * s, cx + ew, cy - h - 0.10 * s), fill=cv.c[colore],
                       width=w)
            if sbatte and umore in ("pronto", "controllo"):
                h *= 0.12                            # palpebre chiuse
            d.ellipse((cx + gx - ew, cy + gy - h, cx + gx + ew, cy + gy + h), fill=cv.c[colore])


def _bocca(cv: Canvas, s: float, x0: float, y0: float, umore: str, t: float, colore: str) -> None:
    d, w = cv.d, cv.stroke
    y = y0 + BOCCA_Y * s
    xs = [x0 + f * s for f in (0.36, 0.43, 0.5, 0.57, 0.64)]
    if umore == "penso":                              # tre puntini che si accendono a turno
        for i, x in enumerate(xs[1:4]):
            acceso = wave(t, 1.2, i / 3) > 0.55 or t == 0.0
            r = 0.028 * s
            d.ellipse((x - r, y - r, x + r, y + r), fill=cv.c[colore if acceso else "line"])
    elif umore == "fatto":                            # sorriso
        d.arc((xs[0], y - 0.12 * s, xs[4], y + 0.06 * s), 20, 160, fill=cv.c[colore], width=w + 1)
    elif umore == "errore":                           # zig-zag
        su = 0.025 * s
        d.line([(x, y + (su if i % 2 else -su)) for i, x in enumerate(xs)], fill=cv.c[colore],
               width=w)
    elif umore == "dubbio":                           # storta
        d.line((xs[1], y + 0.02 * s, xs[3], y - 0.03 * s), fill=cv.c[colore], width=w)
    else:                                             # linea
        d.line((xs[1], y, xs[3], y), fill=cv.c[colore if umore != "offline" else "line"], width=w)


def _antenna(cv: Canvas, s: float, x0: float, y0: float, umore: str, t: float, bg: str) -> None:
    d = cv.d
    ax0, ay0, ax1, ay1 = (x0 + ANTENNA[0] * s, y0 + ANTENNA[1] * s,
                          x0 + ANTENNA[2] * s, y0 + ANTENNA[3] * s)
    d.line((ax0, ay0, ax1, ay1), fill=cv.c["ink"], width=cv.stroke)
    r = PALLINA_R * s
    if umore == "offline":
        colore = "line"
    elif umore == "errore":
        colore = "pink"
    elif umore == "penso":                            # lampeggia: occupato
        colore = "ink" if bg == "orange" else "orange"
        if wave(t, 0.5) < 0.5 and t > 0:
            colore = "line"
    else:
        colore = "amber" if bg == "orange" else "orange"
        if umore in ("pronto", "controllo"):
            r *= 0.85 + 0.3 * wave(t, 1.6)            # pulsa piano
    d.ellipse((ax1 - r, ay1 - r, ax1 + r, ay1 + r), fill=cv.c[colore], outline=cv.c["ink"],
              width=cv.line)


def _segni(cv: Canvas, s: float, x0: float, y0: float, umore: str, t: float) -> None:
    """"?" accanto alla testa (dubbio) e "z" che salgono (offline)."""
    f = font("grotesk", round(0.22 * s), 700)
    if umore == "dubbio":
        cv.text((x0 + 0.92 * s, y0 + 0.17 * s + math.sin(t * 4) * 0.015 * s), "?", f, "ink", "mm")
    elif umore == "offline":
        for i, ch in enumerate("zZ"):
            k = ((t / 2.5) + i * 0.5) % 1.0 if t else i * 0.5
            cv.text((x0 + (0.80 + 0.08 * i) * s, y0 + (0.22 - 0.2 * k) * s), ch,
                    font("grotesk", round((0.12 + 0.07 * i) * s), 700), "ink", "mm")


def draw(cv: Canvas, box: Box | tuple[float, float, float, float], umore: str, t: float = 0.0,
         bg: str = "cream") -> None:
    """Disegna il bot nel riquadro (il lato minore, centrato) per l'istante `t`; `bg` è il fondo."""
    if umore not in MOODS:
        umore = "pronto"
    bx, by, bw, bh = (box.x, box.y, box.w, box.h) if isinstance(box, Box) else (
        box[0], box[1], box[2] - box[0], box[3] - box[1])
    s = min(bw, bh)
    x0, y0 = bx + (bw - s) / 2, by + (bh - s) / 2
    if t:                                             # movimenti del corpo intero
        if umore == "fatto":
            y0 -= abs(math.sin(t * 6)) * 0.035 * s
        elif umore == "errore" and (t % SCUOTE_S) < SCUOTE_DUR:
            x0 += math.sin(t * 45) * 0.03 * s
    colore = {"offline": "line", "errore": "pink"}.get(umore, "amber")
    cv.rect((x0 + TESTA[0] * s, y0 + TESTA[1] * s, x0 + TESTA[2] * s, y0 + TESTA[3] * s), "ink",
            "line", cv.stroke, r=round(TESTA_R * s))
    for o in ORECCHIE:
        cv.rect((x0 + o[0] * s, y0 + o[1] * s, x0 + o[2] * s, y0 + o[3] * s), "ink", r=cv.line)
    _antenna(cv, s, x0, y0, umore, t, bg)
    _occhi(cv, s, x0, y0, umore, t, colore)
    _bocca(cv, s, x0, y0, umore, t, colore)
    _segni(cv, s, x0, y0, umore, t)
