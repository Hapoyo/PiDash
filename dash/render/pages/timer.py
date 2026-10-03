"""Timer: conto alla rovescia grande, barra del tempo residuo e bottoni che sommano il tempo."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from ...layout import Box
from ...widgets.timer import TimerState
from ..canvas import Canvas
from ..theme import GRID, fit, px

if TYPE_CHECKING:
    from ...app import App

BAR_H = 10  # barra del tempo residuo (pixel a 480×320)


def _geometry(b: Box, u: float) -> tuple[Box, Box, Box]:
    """Pannello del tempo, barra, riga dei bottoni: stessa geometria per disegno e tocco."""
    g = px(GRID.gap, u)
    top = Box(b.x, b.y, b.w, round(b.h * 0.58))
    bar = Box(b.x, top.bottom + g, b.w, px(BAR_H, u))
    row = Box(b.x, bar.bottom + g, b.w, b.bottom - bar.bottom - g)
    return top, bar, row


def hits(b: Box, widget: Any, u: float) -> list[tuple[Box, str]]:
    """Bottoni della riga in basso: − · +1' · +5' … · C (fuori dai bottoni: avvia/pausa)."""
    row = _geometry(b, u)[2]
    buttons = widget.buttons()
    g = px(GRID.gap, u)
    n = len(buttons)
    cw = (row.w - (n - 1) * g) / n
    return [(Box(round(row.x + i * (cw + g)), row.y, round(cw), row.h), hit)
            for i, (hit, _) in enumerate(buttons)]


def draw(cv: Canvas, b: Box, app: App, now: datetime) -> None:
    t: Any = app.page.widget
    mm, ss = divmod(t.shown_remaining(), 60)
    pad = cv.pad
    running = t.state is TimerState.RUNNING
    bg = "orange" if running else "cream"
    top, bar, _ = _geometry(b, cv.u)
    # pannello del tempo: nome della durata e stato in alto, minuti:secondi al centro
    cv.solid(top, bg)
    cv.label((top.x + pad, top.y + pad), t.labels.get(t.duration, "timer"), "ink")
    stato = t.state.value.lower()
    if t.state in (TimerState.IDLE, TimerState.PAUSED) and t.remaining() > 0:
        stato += " · tocca per avviare" if app.touch else " · a avvia"
    cv.label((top.right - pad, top.y + pad), stato, "ink", "ra", bold=True)
    head = cv.height(cv.f_label) + cv.gap
    num = Box(top.x + pad, top.y + pad + head, top.w - 2 * pad, top.h - 2 * pad - head)
    tempo, pos = f"{mm:02d}:{ss:02d}", (top.x + top.w / 2, num.bottom)
    f = cv.big(num, tempo, "ink", pos=pos, anchor="ms", slot="timer.tempo", bg=bg, live=True,
               ref="00:00")
    if running:
        cv.colon_fx(tempo, f, pos, "ms", bg)
    # barra del tempo residuo, sul tempo impostato
    frac = t.remaining() / t.duration if t.duration else 0.0
    cv.progress(bar, frac, "amber", track="panel", outline="line", show_empty=False)
    # bottoni: "−" e "C" più tenui, l'ultimo toccato in rosa per un attimo
    boxes = hits(b, t, cv.u)
    testi = dict(t.buttons())
    lampo = t.flashing()
    cw = boxes[0][0].w if boxes else 0
    font = fit("+15'", "grotesk", 600, cw - pad, boxes[0][0].h * 0.5) if boxes else None
    for cb, hit in boxes:
        active = hit == lampo
        tenue = hit in ("sub", "clear")
        cv.key(cb, "pink" if active else "panel", "cream" if active else "line",
               cv.stroke if active else cv.line)
        cv.text((cb.x + cb.w / 2, cb.y + cb.h / 2), testi[hit], font,
                "paper" if active else ("tan" if tenue else "cream"), "mm")
