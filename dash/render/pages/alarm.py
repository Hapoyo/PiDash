"""Sveglia: prossima sveglia in grande, stato, tempo che manca, elenco delle sveglie."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from ...layout import GIORNI, Box
from ..canvas import Canvas
from ..theme import font

if TYPE_CHECKING:
    from ...app import App


def draw(cv: Canvas, b: Box, app: App, now: datetime) -> None:
    u = cv.u
    al: Any = app.page.widget
    nxt = al.next_alarm(now) if al.armed else None
    r, pad, g = round(20 * u), max(4, round(11 * u)), round(10 * u)
    top = Box(b.x, b.y, b.w, round(b.h * 0.52))
    armed = al.armed and nxt is not None
    if armed:
        cv.rect(top, r, "cream")
    else:
        cv.rect(top, r, "panel", "cream", max(1, round(2 * u)))
    col = "ink" if armed else "cream"
    cv.text((top.x + pad, top.y + pad), "sveglia", font("mono", round(12 * u)), col, "la")
    cv.text((top.right - pad, top.y + pad), "armata" if armed else "disarmata",
            font("mono", round(12 * u), 700), col, "ra")
    first = nxt[0] if nxt else (al.alarms[0] if al.alarms else None)
    text = f"{first.hour:02d}:{first.minute:02d}" if first else "--:--"
    num = Box(top.x + pad, top.y + pad + round(14 * u), top.w - 2 * pad,
              top.h - 2 * pad - round(14 * u))
    cv.big(num, text, col, 500, pos=(top.x + top.w / 2, num.bottom), anchor="ms",
           slot="alarm.ora", bg="cream" if armed else "panel")
    rows = Box(b.x, top.bottom + g, b.w, b.bottom - top.bottom - g)
    if nxt:
        delta = nxt[1] - now
        hh, mm = divmod(int(delta.total_seconds()) // 60, 60)
        head = Box(rows.x, rows.y, rows.w, round(rows.h * 0.42))
        cv.rect(head, r, "amber")
        cv.micro((head.x + pad, head.y + round(6 * u)), "prossima", "ink", "la", 11)
        line = f"{GIORNI[nxt[1].weekday()].lower()} · tra {hh}h{mm:02d}"
        cv.text((head.right - pad, head.bottom - round(8 * u)), line,
                font("grotesk", round(head.h * 0.42), 500), "ink", "rd")
        rows = Box(rows.x, head.bottom + g, rows.w, rows.bottom - head.bottom - g)
    lines = [(f"#{i + 1} {a.hour:02d}:{a.minute:02d} · {'on' if a.enabled else 'off'}",
              a.label_days()) for i, a in enumerate(al.alarms)]
    cv.rows(rows, lines, key_color="cream")
