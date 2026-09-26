"""Home: ora, data, luogo, anelli di settimana/mese/anno, alba/tramonto, avanzamento del giorno."""
from __future__ import annotations

import calendar
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ...layout import GIORNI, MESI, Box
from ..canvas import Canvas
from ..theme import fit, font

if TYPE_CHECKING:
    from ...app import App

ANELLI = (("anno", "orange"), ("mese", "amber"), ("settimana", "cream"))  # dall'esterno


def draw(cv: Canvas, b: Box, app: App, now: datetime) -> None:
    u = cv.u
    clock: Any = app.page.widget
    loc = getattr(clock, "location", None)
    name, lat, lon = loc.snapshot() if loc is not None else ("", 0.0, 0.0)
    line = round(17 * u)
    # pila dal basso: due righe di dati, barra, data; il resto all'ora
    rows_h = 2 * line
    bar_h = round(6 * u)
    date_h = round(26 * u)
    rows_y = b.bottom - rows_h
    bar = Box(b.x, rows_y - round(12 * u) - bar_h, b.w, bar_h)
    date_y = bar.y - round(14 * u)
    head = Box(b.x, b.y, b.w, line)
    cv.micro((head.x, head.y), f"loc // {name or 'n/d'}", "cream", "la", 12)
    cv.micro((head.right, head.y), f"{lat:.3f}n {lon:.3f}e", "tan", "ra", 12)
    clock_top = head.bottom + round(6 * u)
    gap = max(4, round(8 * u))
    band = Box(b.x, clock_top, b.w, date_y - date_h - gap - clock_top)
    # anello dei cicli a destra, ora a sinistra nello spazio che resta
    side = min(band.h + date_h, round(b.w * 0.30))
    clock_box = Box(band.x, band.y, band.w - side - gap, band.h)
    ora = now.strftime("%H:%M")
    pos = (clock_box.x + clock_box.w / 2, clock_box.bottom)
    f = cv.big(clock_box, ora, "cream", 500, pos=pos, anchor="ms", slot="clock.ora")
    cv.colon_fx(ora, f, pos, "ms", "panel")
    if clock is not None and side > round(28 * u):
        ring = Box(band.right - side, band.y + (band.h + date_h - side) // 2, side, side)
        _cycles(cv, ring, clock.cycles(now))
    date = f"{GIORNI[now.weekday()]} {now.day:02d} {MESI[now.month - 1]} {now.year}".lower()
    f = fit(date, "grotesk", 500, clock_box.w, date_h)
    cv.text((clock_box.x + clock_box.w / 2, clock_box.bottom + gap), date, f, "tan", "ma")
    label, frac = clock.progress(now) if clock is not None else ("GIORNO", 0.0)
    cv.progress(bar, frac, "orange")
    sun = clock.sun(now) if clock is not None else None
    yday = now.timetuple().tm_yday
    in_year = 366 if calendar.isleap(now.year) else 365
    rows = [(f"{label.lower()} {frac * 100:.0f}%",
             f"alba {sun[0] if sun else '--:--'} · tramonto {sun[1] if sun else '--:--'}"),
            (f"settimana n:{now.isocalendar().week:02d}", f"giorno {yday}/{in_year}")]
    for i, (left, right) in enumerate(rows):
        y = rows_y + i * line
        cv.micro((b.x, y), left, "orange" if i == 0 else "tan", "la", 12)
        cv.micro((b.right, y), right, "cream", "ra", 12)


def _cycles(cv: Canvas, box: Box, cycles: dict[str, float]) -> None:
    """Tre anelli concentrici con una sfera ciascuno: settimana, mese, anno."""
    u = cv.u
    lw = max(2, round(3 * u))
    dot = max(2.0, 3.2 * u)
    leg_h = round(13 * u)
    side = min(box.w, box.h - leg_h)
    cx, cy = box.x + box.w / 2, box.y + (box.h - leg_h) / 2
    for i, (key, col) in enumerate(ANELLI):
        r = side / 2 - dot - i * (lw + max(4, round(6 * u)))
        if r <= lw:
            continue
        cv.ring(Box(round(cx - r), round(cy - r), round(2 * r), round(2 * r)),
                cycles.get(key, 0.0), col, lw, dot)
    # legenda: tre sigle nei colori dei rispettivi anelli
    sigle = [(k[:3], c) for k, c in reversed(ANELLI)]
    f = font("mono", round(11 * u))
    widths = [f.getlength(s + " ") for s, _ in sigle]
    x = cx - sum(widths) / 2
    for (s, col), wdt in zip(sigle, widths):
        cv.text((x, box.bottom - leg_h), s, f, col, "la")
        x += wdt
