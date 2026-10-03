"""Sveglia: prossima sveglia in grande, stato, tempo che manca, elenco delle sveglie."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from ...layout import GIORNI, Box
from ..canvas import Canvas

if TYPE_CHECKING:
    from ...app import App


def draw(cv: Canvas, b: Box, app: App, now: datetime) -> None:
    al: Any = app.page.widget
    nxt = al.next_alarm(now) if al.armed else None
    g, pad = cv.gap, cv.pad
    armed = al.armed and nxt is not None
    bg, col = ("cream", "ink") if armed else ("panel", "cream")
    # pannello dell'ora: acceso se armata, solo contorno se disarmata
    top = Box(b.x, b.y, b.w, round(b.h * 0.54))
    if armed:
        cv.solid(top, bg)
    else:
        cv.rect(top, bg, "cream", cv.stroke)
    cv.label((top.x + pad, top.y + pad), "sveglia", col)
    cv.label((top.right - pad, top.y + pad), "armata" if armed else "disarmata", col, "ra", bold=True)
    head = cv.height(cv.f_label) + g
    first = nxt[0] if nxt else (al.alarms[0] if al.alarms else None)
    text = f"{first.hour:02d}:{first.minute:02d}" if first else "--:--"
    num = Box(top.x + pad, top.y + pad + head, top.w - 2 * pad, top.h - 2 * pad - head)
    cv.big(num, text, col, pos=(top.x + top.w / 2, num.bottom), anchor="ms", slot="alarm.ora",
           bg=bg, ref="00:00")
    rows = Box(b.x, top.bottom + g, b.w, b.bottom - top.bottom - g)
    if nxt:  # quando suona: riga ambra con giorno e tempo che manca
        hh, mm = divmod(int((nxt[1] - now).total_seconds()) // 60, 60)
        head_box = Box(rows.x, rows.y, rows.w, max(cv.px(30), round(rows.h * 0.40)))
        cv.panel(head_box, "amber", "prossima", f"{GIORNI[nxt[1].weekday()].lower()} · tra {hh}h{mm:02d}")
        rows = Box(rows.x, head_box.bottom + g, rows.w, rows.bottom - head_box.bottom - g)
    lines = [(f"#{i + 1} {a.hour:02d}:{a.minute:02d} · {'on' if a.enabled else 'off'}",
              a.label_days()) for i, a in enumerate(al.alarms)]
    cv.rows(rows, lines, key_color="cream")
