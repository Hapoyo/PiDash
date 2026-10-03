"""Impostazioni: schede da aggiungere o togliere, luminosità, calibrazione del touch, spegnimento.

Tre righe con il nome a sinistra e i bottoni a destra, poi il grafico della tensione di
alimentazione (sotto soglia o no, minuto per minuto) e una riga di stato in fondo. `hits`
restituisce gli stessi rettangoli del disegno: il tocco li trova senza ricalcolarli.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from ...layout import Box
from ...power import THRESHOLD_V
from ..canvas import Canvas
from ..theme import GRID, fit, font, px

if TYPE_CHECKING:
    from ...app import App

CHIP_H = 48    # altezza massima di una riga di bottoni (pixel a 480×320): comoda da toccare
NAME_W = 92    # colonna dei nomi delle righe
SEZIONI = ("schede", "luminosità", "sistema")
POWER_H = 30   # riga del grafico della tensione


def _rows(b: Box, u: float) -> tuple[list[Box], Box, Box]:
    """Tre righe di bottoni e il grafico della tensione (senza la colonna dei nomi), stato in fondo."""
    g = px(GRID.gap, u)
    foot_h = font("mono", px(GRID.small, u)).getbbox("Hgjà", anchor="la")[3] + g
    power_h = px(POWER_H, u)
    avail = b.h - foot_h - power_h - g
    h = min(px(CHIP_H, u), (avail - 2 * g) // 3)
    x = b.x + px(NAME_W, u)
    rows = [Box(x, b.y + i * (h + g), b.right - x, h) for i in range(3)]
    power = Box(x, rows[-1].bottom + g, b.right - x, power_h)
    return rows, power, Box(b.x, b.bottom - foot_h + g, b.w, foot_h - g)


def chips(box: Box, n: int, u: float, per_row: int = 0) -> list[Box]:
    """Bottoni affiancati di uguale larghezza nel riquadro."""
    if n <= 0:
        return []
    per_row = per_row or n
    g = px(GRID.gap, u)
    rows = max(1, -(-n // per_row))
    cw = (box.w - (per_row - 1) * g) / per_row
    ch = min((box.h - (rows - 1) * g) / rows, px(CHIP_H, u))
    return [Box(round(box.x + (i % per_row) * (cw + g)), round(box.y + (i // per_row) * (ch + g)),
                round(cw), round(ch)) for i in range(n)]


def _light(row: Box, u: float) -> tuple[Box, Box, Box]:
    """Riga della luminosità: "−", barra, "+"."""
    g = px(GRID.gap, u)
    bw = round(row.h * 1.3)
    minus = Box(row.x, row.y, bw, row.h)
    plus = Box(row.right - bw, row.y, bw, row.h)
    return minus, Box(minus.right + g, row.y, plus.x - g - minus.right - g, row.h), plus


def _system(row: Box, u: float) -> tuple[Box, Box]:
    """Riga del sistema: "calibra touch" a sinistra, "spegni" più piccolo a destra."""
    g = px(GRID.gap, u)
    off_w = round(row.w * 0.4)
    return Box(row.x, row.y, row.w - off_w - g, row.h), Box(row.right - off_w, row.y, off_w, row.h)


def hits(b: Box, widget: Any, u: float) -> list[tuple[Box, str]]:
    rows, _, _ = _rows(b, u)
    out = [(cb, f"voce:{i}") for i, cb in enumerate(chips(rows[0], len(widget.voci()), u))]
    minus, _, plus = _light(rows[1], u)
    calibra, spegni = _system(rows[2], u)
    return out + [(minus, "luce:-10"), (plus, "luce:10"), (calibra, "calibra"), (spegni, "spegni")]


def _button(cv: Canvas, box: Box, text: str, f: Any, fill: str = "panel", ink: str = "cream",
            outline: str = "line") -> None:
    cv.key(box, fill, outline, cv.line)
    cv.text((box.x + box.w / 2, box.y + box.h / 2), text, f, ink, "mm")


def draw(cv: Canvas, b: Box, app: App, now: datetime) -> None:
    widget: Any = app.page.widget
    rows, power_box, foot = _rows(b, cv.u)
    pad = cv.pad
    for name, row in zip(SEZIONI + ("tensione",), rows + [power_box]):
        cv.label((b.x, row.y + row.h / 2), name, "tan", "lm")
    _power(cv, power_box, widget.alimentazione())
    # schede: una voce per tipo, "+" aggiunge, "−" toglie (in tan)
    voci = widget.voci()
    riquadri = chips(rows[0], len(voci), cv.u)
    if riquadri:
        f = fit("− sveglia", "grotesk", 600, riquadri[0].w - 2 * pad, riquadri[0].h * 0.42)
        for voce, cb in zip(voci, riquadri):
            togli = voce.azione == "del"
            _button(cv, cb, ("− " if togli else "+ ") + voce.label, f,
                    ink="tan" if togli else "cream")
    # luminosità: − barra +
    minus, bar, plus = _light(rows[1], cv.u)
    fb = fit("+", "grotesk", 600, minus.w - 2 * pad, minus.h * 0.5)
    _button(cv, minus, "−", fb)
    _button(cv, plus, "+", fb)
    cv.rect(bar, "panel", "line", cv.line)
    level = widget.luce()
    pct = f"{level}%"
    pct_w = round(cv.f_bold.getlength("100%"))
    track = Box(bar.x + pad, bar.y + bar.h // 2 - cv.px(4), bar.w - 3 * pad - pct_w, cv.px(8))
    cv.progress(track, level / 100, "amber")
    cv.label((bar.right - pad, bar.y + bar.h / 2), pct, "cream", "rm", bold=True, lower=False)
    # sistema: calibrazione del touch e spegnimento con conferma
    calibra, spegni = _system(rows[2], cv.u)
    ft = fit("calibra touch", "grotesk", 500, calibra.w - 2 * pad, calibra.h * 0.36)
    _button(cv, calibra, "calibra touch", ft)
    armato = widget.armato()
    cv.rect(spegni, "pink" if armato else "panel", "cream" if armato else "pink", cv.stroke)
    testo = "conferma" if armato else "spegni"
    fs = fit("conferma", "grotesk", 600, spegni.w - 3 * pad - spegni.h * 0.4, spegni.h * 0.36)
    ink = "paper" if armato else "pink"
    r = spegni.h * 0.17
    tw = fs.getlength(testo)
    x0 = spegni.x + (spegni.w - (2 * r + pad + tw)) / 2
    cy = spegni.y + spegni.h / 2
    cv.power((x0 + r, cy), r, ink, cv.stroke)
    cv.text((x0 + 2 * r + pad, cy), testo, fs, ink, "lm")
    if armato:
        cv.add_fx("outline", (spegni.x, spegni.y, spegni.right - 1, spegni.bottom - 1), "paper",
                  "pink", extra=(cv.radius, cv.stroke))
    # riga di stato: messaggio recente, altrimenti versione e tipo di luminosità
    avviso = widget.avviso()
    if armato:
        avviso = "tocca ancora spegni per spegnere il raspberry"
    cv.label((foot.x, foot.bottom), avviso or widget.info(), "orange" if avviso else "tan", "ld",
             small=True)


def _power(cv: Canvas, box: Box, mon: Any) -> None:
    """Grafico della tensione: una colonna per minuto, rosa dove è scesa sotto la soglia."""
    under = mon is not None and mon.under
    cv.rect(box, "panel", "pink" if under else "line", cv.stroke if under else cv.line)
    soglia = f"{THRESHOLD_V:.2f}".replace(".", ",") + " V"
    if mon is None or mon.source is None:
        stato, col = "non misurabile qui", "tan"
    elif under:
        stato, col = f"sotto {soglia}", "pink"
    elif mon.events:
        ora = mon.last_event.strftime("%H:%M") if mon.last_event else "--:--"
        stato, col = f"cali {mon.events} · {ora}", "amber"
    else:
        stato, col = f"ok ≥ {soglia}", "cream"
    pad = cv.pad
    text_w = round(cv.f_bold.getlength("cali 99 · 00:00"))
    cv.label((box.right - pad, box.y + box.h / 2), stato, col, "rm", bold=True, lower=False)
    strip = Box(box.x + pad, box.y + cv.px(5), box.w - 3 * pad - text_w, box.h - 2 * cv.px(5))
    hist = list(mon.history) if mon is not None else []
    if not hist or strip.w <= 0:
        return
    cw = strip.w / len(hist)
    low = max(1, round(strip.h * 0.3))
    for i, v in enumerate(hist):  # None = non campionato, 0 = sopra soglia, 1 = sotto
        if v is None:
            continue
        x0 = strip.x + i * cw
        top = strip.y if v else strip.bottom - low
        cv.d.rectangle((x0, top, x0 + max(1, cw - 1), strip.bottom - 1),
                       fill=cv.c["pink" if v else "line"])
    if under:  # il riquadro lampeggia finché la tensione resta bassa
        cv.add_fx("outline", (box.x, box.y, box.right - 1, box.bottom - 1), "paper", "pink",
                  extra=(cv.radius, cv.stroke))
