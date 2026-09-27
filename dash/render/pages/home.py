"""Home: ora, data, luogo, anelli di settimana/mese/anno, alba/tramonto, avanzamento del giorno.

Colonna sinistra allineata sul bordo: luogo, ora, data, righe in basso; anelli a destra.
"""
from __future__ import annotations

import calendar
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ...layout import GIORNI, MESI, Box
from ..canvas import Canvas
from ..theme import fit

if TYPE_CHECKING:
    from ...app import App

ANELLI = (("anno", "orange"), ("mese", "amber"), ("settimana", "cream"))  # dall'esterno
CLOCK_RAISE = 5  # pixel a 480×320 di cui l'ora sale rispetto al suo riquadro


def draw(cv: Canvas, b: Box, app: App, now: datetime) -> None:
    clock: Any = app.page.widget
    loc = getattr(clock, "location", None)
    name, lat, lon = loc.snapshot() if loc is not None else ("", 0.0, 0.0)
    gap, lab_h, step = cv.gap, cv.height(cv.f_label), cv.row_step()
    # dal basso: due righe di dati, barra della giornata, data
    rows_y = b.bottom - step - lab_h
    bar = Box(b.x, rows_y - gap - cv.px(6), b.w, cv.px(6))
    date_h = cv.px(20)
    date_top = bar.y - gap - date_h
    # in alto: luogo e coordinate
    cv.label((b.x, b.y), f"loc // {name or 'n/d'}", "cream")
    fonte = loc.kind() if loc is not None else ""  # gps / wifi / ip: quanto è affidabile
    coord = f"{lat:.3f}n {lon:.3f}e" + (f" · {fonte}" if fonte in ("gps", "wifi", "ip") else "")
    cv.label((b.right, b.y), coord, "tan", "ra", small=True)
    # in mezzo: ora a sinistra, anelli a destra (alti quanto ora + data)
    band = Box(b.x, b.y + lab_h + gap, b.w, date_top - gap - (b.y + lab_h + gap))
    side = min(band.h + gap + date_h, round(b.w * 0.30))
    # Mezzo passo di griglia in meno sotto l'ora: le cifre tonde scendono un filo sotto la linea
    # di base e la data (ancora "ld") sale un filo sopra la sua riga, e con il riquadro pieno
    # l'ora toccava il giorno (3 px d'aria a 480×320 invece del passo `gap`).
    clock_box = Box(band.x, band.y, band.w - side - 2 * gap, band.h - gap // 2)
    # Stessa taglia, ma la linea di base sale di CLOCK_RAISE: l'ora usa l'aria sotto l'etichetta
    # del luogo (che ha spazio per le gambe delle lettere) e si stacca dalla data.
    ora = now.strftime("%H:%M")
    pos = (clock_box.x, clock_box.bottom - cv.px(CLOCK_RAISE))
    f = cv.big(clock_box, ora, "cream", pos=pos, anchor="ls", slot="clock.ora", ref="00:00")
    cv.colon_fx(ora, f, pos, "ls", "panel")
    if clock is not None and side > cv.px(40):
        _cycles(cv, Box(b.right - side, band.y, side, band.h + gap + date_h), clock.cycles(now))
    date = f"{GIORNI[now.weekday()]} {now.day:02d} {MESI[now.month - 1]} {now.year}".lower()
    cv.text((b.x, date_top + date_h), date, fit(date, "grotesk", 500, clock_box.w, date_h), "tan", "ld")
    label, frac = clock.progress(now) if clock is not None else ("GIORNO", 0.0)
    cv.progress(bar, frac, "orange")
    sun = clock.sun(now) if clock is not None else None
    yday = now.timetuple().tm_yday
    in_year = 366 if calendar.isleap(now.year) else 365
    rows = [(f"{label.lower()} {frac * 100:.0f}%",
             f"alba {sun[0] if sun else '--:--'} · tramonto {sun[1] if sun else '--:--'}"),
            (f"settimana {now.isocalendar().week:02d}", f"giorno {yday}/{in_year}")]
    for i, (left, right) in enumerate(rows):
        y = rows_y + i * step
        cv.label((b.x, y), left, "orange" if i == 0 else "tan")
        cv.label((b.right, y), right, "cream", "ra")


def _cycles(cv: Canvas, box: Box, cycles: dict[str, float]) -> None:
    """Tre anelli concentrici con una sfera ciascuno (anno, mese, settimana) e legenda sotto."""
    lw = cv.stroke
    dot = cv.px(3.2)
    leg_h = cv.height(cv.f_small) + cv.px(4)
    side = min(box.w, box.h - leg_h)
    cx, cy = box.x + box.w / 2, box.y + (box.h - leg_h) / 2
    for i, (key, col) in enumerate(ANELLI):
        r = side / 2 - dot - i * (lw + cv.px(5))
        if r <= lw:
            continue
        cv.ring(Box(round(cx - r), round(cy - r), round(2 * r), round(2 * r)),
                cycles.get(key, 0.0), col, lw, dot)
    # legenda: tre sigle nei colori dei rispettivi anelli, centrate sotto
    sigle = [(k[:3], c) for k, c in reversed(ANELLI)]
    widths = [cv.f_small.getlength(s + " ") for s, _ in sigle]
    x = cx - (sum(widths) - cv.f_small.getlength(" ")) / 2
    for (s, col), wdt in zip(sigle, widths):
        cv.label((x, box.bottom), s, col, "ld", small=True)
        x += wdt
