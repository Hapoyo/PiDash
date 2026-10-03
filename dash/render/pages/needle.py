"""Needle: stato del servizio, ultima frase con la funzione riconosciuta e frasi da provare.

Pannello in alto (bot, stato, frase, funzione, barra della confidenza) e in basso i bottoni con
le frasi di `needle.queries`. Il bot (`render/bot.py`) mostra l'umore del widget: pronto, penso,
fatto, dubbio, errore, offline. `hits` restituisce gli stessi rettangoli del disegno.
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

BAR_H = 10  # barra della confidenza (pixel a 480×320)


def _geometry(b: Box, u: float) -> tuple[Box, Box]:
    """Pannello dell'esito e area dei bottoni: stessa geometria per disegno e tocco."""
    g = px(GRID.gap, u)
    top = Box(b.x, b.y, b.w, round(b.h * 0.63))
    return top, Box(b.x, top.bottom + g, b.w, b.bottom - top.bottom - g)


def hits(b: Box, widget: Any, u: float) -> list[tuple[Box, str]]:
    """Un bottone per frase, due per riga."""
    grid = _geometry(b, u)[1]
    return [(cb, f"q:{i}") for i, cb in enumerate(chips(grid, len(widget.queries), u, per_row=2))]


def draw(cv: Canvas, b: Box, app: App, now: datetime) -> None:
    w: Any = app.page.widget
    online, busy, last = w.snapshot()
    top, _ = _geometry(b, cv.u)
    pad = cv.pad
    bg = "orange" if busy else ("cream" if online else "tan")
    cv.rect(top, bg)
    # barra della confidenza in fondo al pannello
    bar = Box(top.x + pad, top.bottom - pad - cv.px(BAR_H), top.w - 2 * pad, cv.px(BAR_H))
    conf = last.confidenza if last and last.confidenza is not None else 0.0
    cv.progress(bar, conf, "amber", track="panel", outline="line", show_empty=False)
    # il bot a sinistra (quadrato, alto quanto il pannello sopra la barra), il testo a destra
    lato = bar.y - cv.gap - (top.y + pad)
    mascotte = Box(top.x + pad, top.y + pad, lato, lato)
    umore = w.umore()
    bot.draw(cv, mascotte, umore, 0.0, bg)
    cv.add_fx("bot", mascotte.rect, bg=bg, extra=(float(bot.MOODS.index(umore)),))
    sx = mascotte.right + 2 * cv.gap
    # intestazione: a sinistra cosa ha fatto il dashboard con l'ultima frase, se ha fatto qualcosa;
    # a destra lo stato
    esito = last.esito if last else ""
    cv.label((sx, top.y + pad), "→ " + esito if esito else "needle · function calling",
             "ink", bold=bool(esito))
    cv.label((top.right - pad, top.y + pad), w.stato(), "ink", "ra", bold=True)
    head = cv.height(cv.f_label) + cv.gap
    body = Box(sx, top.y + pad + head, top.right - pad - sx, bar.y - cv.gap - (top.y + pad + head))
    if last is None:
        msg = "servizio spento: systemctl start needle" if online is False else \
              "tocca una frase per provare"
        cv.label((body.x, body.y), msg, "ink")
    else:
        # frase (a sinistra) e tempo di risposta (a destra), poi la funzione in grande
        line = cv.height(cv.f_label) + cv.gap
        tempo = f"{last.confidenza * 100:.0f}% · {last.ms / 1000:.1f} s".replace(".", ",") \
            if last.confidenza is not None else f"{last.ms / 1000:.1f} s".replace(".", ",")
        cv.label((body.x, body.y), last.domanda, "ink")
        cv.label((body.right, body.y), tempo, "ink", "ra", lower=False)
        esito = " · ".join(last.chiamate) or last.errore or "nessuna funzione"
        area = Box(body.x, body.y + line, body.w, body.h - line)
        cv.big(area, esito, "ink")
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
