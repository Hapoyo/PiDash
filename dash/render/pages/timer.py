"""Timer: conto alla rovescia grande, barra del tempo residuo e preset selezionabili."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from ...layout import Box
from ...widgets.timer import TimerState
from ..canvas import Canvas
from ..theme import font

if TYPE_CHECKING:
    from ...app import App


def draw(cv: Canvas, b: Box, app: App, now: datetime) -> None:
    u = cv.u
    t: Any = app.page.widget
    mm, ss = divmod(t.shown_remaining(), 60)
    r, pad, g = round(20 * u), max(4, round(11 * u)), round(10 * u)
    running = t.state is TimerState.RUNNING
    bg = "orange" if running else "cream"
    top = Box(b.x, b.y, b.w, round(b.h * 0.58))
    cv.rect(top, r, bg)
    cv.micro((top.x + pad, top.y + pad), t.label(), "ink", "la", 12)
    cv.micro((top.right - pad, top.y + pad), t.state.value.lower(), "ink", "ra", 12)
    num = Box(top.x + pad, top.y + pad + round(14 * u), top.w - 2 * pad,
              top.h - 2 * pad - round(14 * u))
    tempo, pos = f"{mm:02d}:{ss:02d}", (top.x + top.w / 2, num.bottom)
    f = cv.big(num, tempo, "ink", 500, pos=pos, anchor="ms", slot="timer.tempo", bg=bg, live=True)
    if running:
        cv.colon_fx(tempo, f, pos, "ms", bg)
    # barra del tempo residuo
    bar = Box(b.x, top.bottom + g, b.w, max(round(10 * u), round(b.h * 0.1)))
    frac = t.remaining() / t.duration if t.duration else 0.0
    cv.progress(bar, frac, "amber", track="panel", outline="line", width=max(1, round(2 * u)),
                show_empty=False)
    # preset: quello attivo in evidenza
    row = Box(b.x, bar.bottom + g, b.w, b.bottom - bar.bottom - g)
    n = len(t.presets)
    cw = (row.w - (n - 1) * g) / n
    for i, preset in enumerate(t.presets):
        cb = Box(round(row.x + i * (cw + g)), row.y, round(cw), row.h)
        active = i == t.preset_idx
        cv.rect(cb, r, "pink" if active else "panel", "cream" if active else "line",
                max(1, round(2 * u)))
        cv.text((cb.x + cb.w / 2, cb.y + cb.h / 2), f"{preset // 60}'",
                font("grotesk", round(cb.h * 0.5), 600), "paper" if active else "cream", "mm")
