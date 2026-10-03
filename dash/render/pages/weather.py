"""Meteo: temperatura, vento con anello della direzione, valori, previsione oraria, sole e luna."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from ...layout import Box
from ...widgets.weather import (SHORT, beaufort, describe, moon_illumination, moon_name,
                                moon_phase, rosa, vento_nome)
from ..canvas import Canvas
from ..theme import fit

if TYPE_CHECKING:
    from ...app import App


def draw(cv: Canvas, b: Box, app: App, now: datetime) -> None:
    wx: Any = app.page.widget
    data = wx.snapshot()
    if not data:
        cv.label((b.x + b.w / 2, b.y + b.h / 2), "meteo in attesa di dati...", "tan", "mm")
        return
    cur = data["current"]
    idx = wx.hour_index(data)
    g, pad = cv.gap, cv.pad
    text, icon = describe(int(cur.get("weather_code", -1)))
    kn = float(cur.get("wind_speed_10m", 0.0))
    deg = float(cur.get("wind_direction_10m", 0.0))
    gust = float(cur.get("wind_gusts_10m", 0.0))
    rain = float(wx.hourly(data, "precipitation_probability", idx) or 0)
    foot_h = cv.height(cv.f_small)
    # riga 1: temperatura (crema) e vento (arancio) con l'anello della direzione
    top_h = round(b.h * 0.44)
    left = Box(b.x, b.y, round((b.w - g) * 0.45), top_h)
    right = Box(left.right + g, b.y, b.right - left.right - g, top_h)
    ic = min(left.h - 2 * pad, round(left.w * 0.34))  # icona a destra, nello spazio libero
    cv.panel(left, "cream", SHORT.get(text, text), f"{float(cur.get('temperature_2m', 0)):.0f}°",
             f"percepita {float(cur.get('apparent_temperature', 0)):.0f}°", ref="-00°",
             reserve=ic + g if ic > cv.px(30) else 0, slot="weather.temp")
    if ic > cv.px(30):
        cv.icon(icon, Box(left.right - pad - ic, left.y + (left.h - ic) // 2, ic, ic), "ink", "cream")
    side = min(right.h - 2 * pad, round(right.w * 0.36))
    mostra = side > cv.px(34)
    cv.panel(right, "orange", f"vento {vento_nome(deg).lower()}", f"{kn:.0f} kn",
             f"{rosa(deg).lower()} · raf {gust:.0f} · f{beaufort(kn)}", ref="00 kn",
             reserve=side + g if mostra else 0, slot="weather.vento")
    if mostra:
        _wind_ring(cv, Box(right.right - pad - side, right.y + (right.h - side) // 2, side, side), deg)
    # riga 2: tre valori su una riga ciascuno (etichetta … numero)
    mid = Box(b.x, left.bottom + g, b.w, max(cv.px(28), round(b.h * 0.14)))
    cw = (mid.w - 2 * g) / 3
    cells = [("pioggia", f"{rain:.0f}%", "pink"),
             ("umidità", f"{cur.get('relative_humidity_2m', 0):.0f}%", "tan"),
             ("pressione", f"{cur.get('pressure_msl', 0):.0f}", "amber")]
    for i, (k, v, col) in enumerate(cells):
        cb = Box(round(mid.x + i * (cw + g)), mid.y, round(cw), mid.h)
        cv.panel(cb, col, k, v, ref="1013", slot=f"weather.{k}")
    # riga 4 (in fondo): sole e luna
    cv.label((b.x, b.bottom), f"alba {_hhmm(wx.daily(data, 'sunrise'))} · "
             f"tramonto {_hhmm(wx.daily(data, 'sunset'))}", "cream", "ld", small=True)
    phase = moon_phase(now)
    cv.label((b.right, b.bottom), f"luna {moon_name(phase).lower()} "
             f"{moon_illumination(phase) * 100:.0f}%", "tan", "rd", small=True)
    # riga 3: previsione oraria fra i valori e il piede
    fc = Box(b.x, mid.bottom + g, b.w, b.bottom - foot_h - g - (mid.bottom + g))
    _forecast(cv, fc, wx, data, idx)


def _forecast(cv: Canvas, fc: Box, wx: Any, data: dict[str, Any], idx: int) -> None:
    """Cinque colonne ogni 3 ore: ora, temperatura, vento e pioggia (se c'è spazio)."""
    cv.rect(fc, "panel", "line")
    times: list[str] = data.get("hourly", {}).get("time", [])
    steps = [n for n in (3, 6, 9, 12, 15) if idx + n < len(times)]
    if not steps:
        return
    small_h = cv.height(cv.f_small)
    inner = fc.inset(cv.px(4), cv.px(5))
    dettaglio = inner.h >= 2 * small_h + cv.px(22)  # terza riga solo se il numero resta leggibile
    num = Box(0, inner.y + small_h + cv.px(3), 0,
              inner.h - small_h - cv.px(3) - (small_h + cv.px(3) if dettaglio else 0))
    cw = fc.w / len(steps)
    f = fit("-00°", "grotesk", 500, cw - 2 * cv.pad, num.h)
    for i, n in enumerate(steps):
        x = fc.x + i * cw + cw / 2
        t = wx.hourly(data, "temperature_2m", idx + n)
        cv.label((x, inner.y), f"{times[idx + n][11:13]}h", "tan", "ma", small=True)
        cv.text((x, num.bottom), f"{t:.0f}°" if t is not None else "--", f, "cream", "ms")
        if dettaglio:
            kn = wx.hourly(data, "wind_speed_10m", idx + n) or 0
            p = wx.hourly(data, "precipitation_probability", idx + n) or 0
            cv.label((x, inner.bottom), f"{kn:.0f}kn {p:.0f}%", "amber", "md", small=True)
        if i:
            xl = round(fc.x + i * cw)
            cv.d.line((xl, inner.y, xl, inner.bottom), fill=cv.c["line"])


def _hhmm(iso: Any) -> str:
    """"2026-09-24T06:52" → "06:52"."""
    return str(iso or "--:--")[-5:]


def _wind_ring(cv: Canvas, box: Box, deg: float, color: str = "ink", bg: str = "orange") -> None:
    """Direzione del vento come gli anelli della home: arco da nord (ore 12) in senso orario
    fino alla direzione da cui soffia il vento, sfera in testa, gradi al centro."""
    side = min(box.w, box.h)
    lw = cv.stroke
    dot = cv.px(3.2)
    r = side / 2 - dot
    cx, cy = box.x + box.w / 2, box.y + box.h / 2
    ring = Box(round(cx - r), round(cy - r), round(2 * r), round(2 * r))
    cv.ring(ring, (deg % 360) / 360, color, lw, dot, cv.mix(color, bg, 0.65), bg)
    cv.d.line((cx, ring.y - lw, cx, ring.y + lw * 2), fill=cv.c[color], width=lw)  # tacca del nord
    f = fit("360°", "grotesk", 500, r * 1.3, r * 0.6)
    cv.text((cx, cy + f.size * 0.35), f"{deg % 360:.0f}°", f, color, "ms")
