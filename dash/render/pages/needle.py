"""Needle: stato del servizio, esito dell'ultima frase, bot e frasi da provare.

In alto una riga con cosa ha fatto il dashboard (a sinistra) e lo stato del servizio (a destra);
sotto, a sinistra, il bot nel pannello colorato dallo stato e, a destra, i bottoni con le frasi
di `needle.queries`. Il bot (`render/bot.py`) mostra l'umore del widget: pronto, penso, fatto,
dubbio, errore, offline. `hits` restituisce gli stessi rettangoli del disegno.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from ...layout import Box
from .. import bot
from ..canvas import Canvas
from ..theme import GRID, fit, px
from .new import chips

if TYPE_CHECKING:
    from ...app import App

LABEL_H = 12      # riga dell'intestazione (pixel a 480×320, corpo di `cv.label`)
BOT_W = 0.4       # larghezza massima del pannello del bot, in frazioni della pagina


def _geometry(b: Box, u: float) -> tuple[Box, Box]:
    """Pannello del bot e colonna dei bottoni: stessa geometria per disegno e tocco."""
    g = px(GRID.gap, u)
    y = b.y + px(LABEL_H, u) + 2 * g
    h = b.bottom - y
    side = min(h, round(b.w * BOT_W))
    panel = Box(b.x, y, side, h)
    return panel, Box(panel.right + g, y, b.right - panel.right - g, h)


def hits(b: Box, widget: Any, u: float) -> list[tuple[Box, str]]:
    """Un bottone per frase: una colonna fino a quattro frasi, poi due per riga."""
    grid = _geometry(b, u)[1]
    n = len(widget.queries)
    return [(cb, f"q:{i}") for i, cb in enumerate(chips(grid, n, u, per_row=1 if n <= 4 else 2))]


def draw(cv: Canvas, b: Box, app: App, now: datetime) -> None:
    w: Any = app.page.widget
    online, busy, last = w.snapshot()
    panel, _ = _geometry(b, cv.u)
    pad = cv.pad
    # intestazione: a sinistra cosa ha fatto il dashboard con l'ultima frase, a destra lo stato
    esito = last.esito if last else ""
    if esito:
        cv.label((b.x, b.y), "→ " + esito, "cream", bold=True)
    elif last is None:
        cv.label((b.x, b.y), "servizio spento: systemctl start needle" if online is False else
                 "tocca una frase per provare", "tan")
    else:
        cv.label((b.x, b.y), "needle · function calling", "tan")
    cv.label((b.right, b.y), w.stato(), "cream", "ra", bold=True)
    # il bot, quadrato e centrato nel pannello colorato dallo stato
    bg = "orange" if busy else ("cream" if online else "tan")
    cv.rect(panel, bg)
    lato = min(panel.w, panel.h) - 2 * pad
    mascotte = Box(round(panel.x + (panel.w - lato) / 2), round(panel.y + (panel.h - lato) / 2),
                   lato, lato)
    umore = w.umore()
    bot.draw(cv, mascotte, umore, 0.0, bg)
    cv.add_fx("bot", mascotte.rect, bg=bg, extra=(float(bot.MOODS.index(umore)),))
    # frasi da provare: la scelta da tastiera ha il bordo ambra, l'ultima toccata è rosa
    boxes = hits(b, w, cv.u)
    if not boxes:
        return
    cw, ch = boxes[0][0].w, boxes[0][0].h
    f = fit(max(w.queries, key=len), "grotesk", 500, cw - 2 * pad, ch * 0.42)
    lampo = w.flashing()
    attivo = online and not busy
    for i, (cb, _) in enumerate(boxes):
        toccata = i == lampo
        cv.rect(cb, "pink" if toccata else "panel",
                "cream" if toccata else ("amber" if i == w.idx else "line"),
                cv.stroke if toccata else cv.line)
        cv.text((cb.x + cb.w / 2, cb.y + cb.h / 2), w.queries[i], f,
                "paper" if toccata else ("cream" if attivo else "tan"), "mm")
