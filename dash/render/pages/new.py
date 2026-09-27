"""Scheda "+": schede opzionali da aggiungere o togliere, "+" grande in testa."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from ...layout import Box
from ..canvas import Canvas
from ..theme import GRID, fit, px

if TYPE_CHECKING:
    from ...app import App

CHIP_H = 48  # altezza massima di una voce (pixel a 480×320): un tasto comodo da toccare


def grid(b: Box, u: float) -> Box:
    """Zona del catalogo: sotto il riquadro con il "+"."""
    top_h = round(b.h * 0.38)
    g = px(GRID.gap, u)
    return Box(b.x, b.y + top_h + g, b.w, b.h - top_h - g)


def chips(box: Box, n: int, u: float, per_row: int = 0) -> list[Box]:
    """Riquadri del catalogo: stessa geometria per disegno e tocco."""
    if n <= 0:
        return []
    per_row = per_row or min(3, n)
    g = px(GRID.gap, u)
    rows = max(1, -(-n // per_row))
    cw = (box.w - (per_row - 1) * g) / per_row
    ch = min((box.h - (rows - 1) * g) / rows, px(CHIP_H, u))
    return [Box(round(box.x + (i % per_row) * (cw + g)), round(box.y + (i // per_row) * (ch + g)),
                round(cw), round(ch)) for i in range(n)]


def hits(b: Box, widget: Any, u: float) -> list[tuple[Box, str]]:
    """Bottoni della scheda: un tocco su una voce la esegue."""
    riquadri = chips(grid(b, u), len(widget.voci()), u)
    return [(cb, f"voce:{i}") for i, cb in enumerate(riquadri)]


def draw(cv: Canvas, b: Box, app: App, now: datetime) -> None:
    widget: Any = app.page.widget
    voci = widget.voci()
    scelta = widget.scelta()
    g, pad = cv.gap, cv.pad
    # riquadro in testa: "+" grande a sinistra, voce scelta a destra
    top = Box(b.x, b.y, b.w, grid(b, cv.u).y - g - b.y)
    cv.rect(top, "cream")
    plus = Box(top.x + pad, top.y + pad, top.h - 2 * pad, top.h - 2 * pad)
    cv.big(plus, "+", "ink", 600, pos=(plus.x + plus.w / 2, plus.bottom), anchor="ms")
    text_x = plus.right + 2 * g
    cv.label((text_x, top.y + pad), "schede da aggiungere", "ink")
    cv.label((top.right - pad, top.y + pad), "tocca il +" if app.touch else "a conferma",
             "ink", "ra", small=True)
    if scelta is not None:
        azione = "aggiungi" if scelta.azione == "add" else "togli"  # la voce fa da interruttore
        testo = f"{azione} {scelta.label}"
        room = Box(text_x, top.y + pad, top.right - pad - text_x, top.h - 2 * pad)
        head = cv.height(cv.f_label) + g
        cv.text((text_x, room.bottom), testo,   # "ld": le gambe della g restano nel pannello
                fit(testo, "grotesk", 500, room.w, room.h - head), "ink", "ld")
    # voci: una per tipo, quella scelta in rosa
    riquadri = chips(grid(b, cv.u), len(voci), cv.u)
    for i, (voce, cb) in enumerate(zip(voci, riquadri)):
        active = scelta is not None and i == widget.idx % len(voci)
        if active:
            cv.add_fx("outline", (cb.x, cb.y, cb.right - 1, cb.bottom - 1), "paper", "pink",
                      extra=(cv.radius, cv.stroke))
        togli = voce.azione == "del"
        cv.rect(cb, "pink" if active else "panel", "cream" if active else "line",
                cv.stroke if active else cv.line)
        testo = ("− " if togli else "+ ") + voce.label
        cv.text((cb.x + cb.w / 2, cb.y + cb.h / 2), testo,
                fit(f"− {voce.label}", "grotesk", 600, cb.w - 2 * pad, cb.h * 0.45),
                "paper" if active else ("tan" if togli else "cream"), "mm")
    if riquadri:  # sotto le voci: come funziona l'interruttore
        cv.label((b.x + b.w / 2, riquadri[-1].bottom + g), "la stessa voce toglie la scheda "
                 "quando è già nello schedario", "tan", "ma", small=True)
