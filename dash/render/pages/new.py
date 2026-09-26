"""Scheda "+": schede opzionali da aggiungere o togliere, "+" grande in testa."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from ...layout import Box
from ..canvas import Canvas
from ..theme import fit

if TYPE_CHECKING:
    from ...app import App


def grid(b: Box, u: float) -> Box:
    """Zona del catalogo: sotto il riquadro con il "+"."""
    top_h = round(b.h * 0.34)
    g = round(10 * u)
    return Box(b.x, b.y + top_h + g, b.w, b.h - top_h - g)


def chips(box: Box, n: int, u: float, per_row: int = 0) -> list[Box]:
    """Riquadri del catalogo: stessa geometria per disegno e tocco."""
    if n <= 0:
        return []
    per_row = per_row or min(3, n)
    g = round(10 * u)
    rows = max(1, -(-n // per_row))
    cw = (box.w - (per_row - 1) * g) / per_row
    ch = min((box.h - (rows - 1) * g) / rows, 90 * u)  # riquadri alti al massimo come un tasto
    return [Box(round(box.x + (i % per_row) * (cw + g)), round(box.y + (i // per_row) * (ch + g)),
                round(cw), round(ch)) for i in range(n)]


def draw(cv: Canvas, b: Box, app: App, now: datetime) -> None:
    u = cv.u
    widget: Any = app.page.widget
    voci = widget.voci()
    scelta = widget.scelta()
    r, pad = round(20 * u), max(4, round(11 * u))
    top = Box(b.x, b.y, b.w, round(b.h * 0.34))
    cv.rect(top, r, "cream")
    cv.micro((top.x + pad, top.y + pad), "schede da aggiungere", "ink", "la", 12)
    cv.micro((top.right - pad, top.y + pad),
             "tocca il + per confermare" if app.touch else "a conferma · b scegli", "ink", "ra", 11)
    num = Box(top.x + pad, top.y + pad + round(14 * u), round(top.h * 0.7),
              top.h - 2 * pad - round(14 * u))
    cv.big(num, "+", "ink", 600, pos=(top.x + pad + num.w / 2, num.bottom), anchor="ms")
    if scelta is not None:
        azione = "aggiungi" if scelta.azione == "add" else "togli"  # la voce fa da interruttore
        f = fit(f"{azione} {scelta.label}", "grotesk", 500, top.w - num.w - 3 * pad, num.h * 0.62)
        cv.text((top.right - pad, num.bottom), f"{azione} {scelta.label}", f, "ink", "rs")
    riquadri = chips(grid(b, u), len(voci), u)
    if riquadri:  # sotto i riquadri: come funziona l'interruttore
        cv.micro((b.x + b.w / 2, riquadri[-1].bottom + round(14 * u)),
                 "la stessa voce toglie la scheda quando è già nello schedario", "tan", "ma", 11)
    for i, (voce, cb) in enumerate(zip(voci, riquadri)):
        active = scelta is not None and i == widget.idx % len(voci)
        if active:
            cv.add_fx("outline", (cb.x, cb.y, cb.right - 1, cb.bottom - 1), "paper", "pink",
                      extra=(r, max(1, round(2 * u))))
        togli = voce.azione == "del"
        cv.rect(cb, r, "pink" if active else "panel", "cream" if active else "line",
                max(1, round(2 * u)))
        col = "paper" if active else ("tan" if togli else "cream")
        cv.text((cb.x + cb.w / 2, cb.y + cb.h / 2 - round(3 * u)), ("− " if togli else "+ ") + voce.label,
                fit(f"− {voce.label}", "grotesk", 600, cb.w - round(12 * u), cb.h * 0.42), col, "mm")
