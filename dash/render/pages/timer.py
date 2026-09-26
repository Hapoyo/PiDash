"""Timer: conto alla rovescia grande, barra del tempo residuo e preset selezionabili."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from ...layout import Box
from ...widgets.timer import TimerState
from ..canvas import Canvas
from ..theme import fit

if TYPE_CHECKING:
    from ...app import App


def draw(cv: Canvas, b: Box, app: App, now: datetime) -> None:
    t: Any = app.page.widget
    mm, ss = divmod(t.shown_remaining(), 60)
    g, pad = cv.gap, cv.pad
    running = t.state is TimerState.RUNNING
    bg = "orange" if running else "cream"
    # pannello del tempo: nome del preset e stato in alto, minuti:secondi al centro
    top = Box(b.x, b.y, b.w, round(b.h * 0.58))
    cv.rect(top, bg)
    cv.label((top.x + pad, top.y + pad), t.labels.get(t.duration, "timer"), "ink")
    cv.label((top.right - pad, top.y + pad), t.state.value.lower(), "ink", "ra", bold=True)
    head = cv.height(cv.f_label) + g
    num = Box(top.x + pad, top.y + pad + head, top.w - 2 * pad, top.h - 2 * pad - head)
    tempo, pos = f"{mm:02d}:{ss:02d}", (top.x + top.w / 2, num.bottom)
    f = cv.big(num, tempo, "ink", pos=pos, anchor="ms", slot="timer.tempo", bg=bg, live=True,
               ref="00:00")
    if running:
        cv.colon_fx(tempo, f, pos, "ms", bg)
    # barra del tempo residuo
    bar = Box(b.x, top.bottom + g, b.w, cv.px(10))
    frac = t.remaining() / t.duration if t.duration else 0.0
    cv.progress(bar, frac, "amber", track="panel", outline="line", show_empty=False)
    # preset: quello attivo in evidenza
    row = Box(b.x, bar.bottom + g, b.w, b.bottom - bar.bottom - g)
    n = len(t.presets)
    cw = (row.w - (n - 1) * g) / n
    f = fit("00'", "grotesk", 600, cw - 2 * pad, row.h * 0.5)
    for i, preset in enumerate(t.presets):
        cb = Box(round(row.x + i * (cw + g)), row.y, round(cw), row.h)
        active = i == t.preset_idx
        cv.rect(cb, "pink" if active else "panel", "cream" if active else "line",
                cv.stroke if active else cv.line)
        cv.text((cb.x + cb.w / 2, cb.y + cb.h / 2), f"{preset // 60}'", f,
                "paper" if active else "cream", "mm")
