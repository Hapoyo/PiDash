"""Meteo: temperatura, vento con anello della direzione, valori, previsione oraria, sole e luna."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from ...layout import Box
from ...widgets.weather import (SHORT, beaufort, describe, moon_illumination, moon_name,
                                moon_phase, rosa, vento_nome)
from ..canvas import Canvas
from ..theme import fit, font

if TYPE_CHECKING:
    from ...app import App


def draw(cv: Canvas, b: Box, app: App, now: datetime) -> None:
    u = cv.u
    wx: Any = app.page.widget
    data = wx.snapshot()
    if not data:
        cv.micro((b.x + b.w / 2, b.y + b.h / 2), "meteo in attesa di dati...", "tan", "mm", 13)
        return
    cur = data["current"]
    idx = wx.hour_index(data)
    g = round(10 * u)
    text, _ = describe(int(cur.get("weather_code", -1)))
    kn = float(cur.get("wind_speed_10m", 0.0))
    deg = float(cur.get("wind_direction_10m", 0.0))
    gust = float(cur.get("wind_gusts_10m", 0.0))
    rain = float(wx.hourly(data, "precipitation_probability", idx) or 0)
    r = round(20 * u)
    # riga 1: temperatura (crema) e vento (arancio)
    top_h = round(b.h * 0.42)
    left = Box(b.x, b.y, round(b.w * 0.46), top_h)
    right = Box(left.right + g, b.y, b.right - left.right - g, top_h)
    cv.panel(left, "cream", SHORT.get(text, text), f"{float(cur.get('temperature_2m', 0)):.0f}°",
             f"percepita {float(cur.get('apparent_temperature', 0)):.0f}°", r, slot="weather.temp")
    pad = max(4, round(11 * u))
    band_y = right.y + pad + round(16 * u)                      # sotto l'etichetta
    band_h = right.h - (band_y - right.y) - pad - round(22 * u)  # sopra la riga di dettaglio
    comp = min(band_h, round(right.w * 0.34))
    mostra = comp > round(26 * u)
    cv.panel(right, "orange", f"vento {vento_nome(deg).lower()}", f"{kn:.0f} kn",
             f"{rosa(deg).lower()} · raf {gust:.0f} · f{beaufort(kn)}", r,
             reserve=comp + pad if mostra else 0, slot="weather.vento")
    if mostra:
        _wind_ring(cv, Box(right.right - pad - comp, band_y + (band_h - comp) // 2, comp, comp), deg)
    # riga 2: tre valori
    mid = Box(b.x, top_h + b.y + g, b.w, round(b.h * 0.16))
    cw = (mid.w - 2 * g) / 3
    cells = [("pioggia", f"{rain:.0f}%", "pink"),
             ("umidità", f"{cur.get('relative_humidity_2m', 0):.0f}%", "tan"),
             ("pressione", f"{cur.get('pressure_msl', 0):.0f}", "amber")]
    for i, (k, v, col) in enumerate(cells):
        cb = Box(round(mid.x + i * (cw + g)), mid.y, round(cw), mid.h)
        cv.panel(cb, col, k, v, "", r, ref="1013", slot=f"weather.{k}")
    # riga 3: previsione oraria
    fc_top = mid.bottom + g
    foot_h = round(20 * u)
    fc = Box(b.x, fc_top, b.w, b.bottom - fc_top - foot_h - g)
    cv.rect(fc, r, "panel", "line", max(1, round(2 * u)))
    times: list[str] = data.get("hourly", {}).get("time", [])
    steps = [n for n in (3, 6, 9, 12, 15) if idx + n < len(times)]
    cw = fc.w / max(1, len(steps))
    for i, n in enumerate(steps):
        x = fc.x + i * cw
        t = wx.hourly(data, "temperature_2m", idx + n)
        kn2 = wx.hourly(data, "wind_speed_10m", idx + n) or 0
        p = wx.hourly(data, "precipitation_probability", idx + n) or 0
        cv.micro((x + cw / 2, fc.y + round(8 * u)), f"{times[idx + n][11:13]}h", "tan", "ma", 11)
        cv.text((x + cw / 2, fc.y + fc.h * 0.62), f"{t:.0f}°" if t is not None else "--",
                font("grotesk", round(fc.h * 0.34), 500), "cream", "ms")
        cv.micro((x + cw / 2, fc.bottom - round(8 * u)), f"{kn2:.0f}kn · {p:.0f}%", "amber", "md", 11)
        if i:
            cv.d.line((x, fc.y + round(8 * u), x, fc.bottom - round(8 * u)), fill=cv.c["line"])
    # riga 4: sole e luna
    phase = moon_phase(now)
    sunrise = str(wx.daily(data, "sunrise") or "")[-5:]
    sunset = str(wx.daily(data, "sunset") or "")[-5:]
    cv.micro((b.x, b.bottom - round(6 * u)), f"alba {sunrise} · tramonto {sunset}", "cream", "ld", 12)
    cv.micro((b.right, b.bottom - round(6 * u)),
             f"luna {moon_name(phase).lower()} {moon_illumination(phase) * 100:.0f}%", "tan", "rd", 12)


def _wind_ring(cv: Canvas, box: Box, deg: float, color: str = "ink", bg: str = "orange") -> None:
    """Direzione del vento come gli anelli della home: arco da nord (ore 12) in senso orario
    fino alla direzione da cui soffia il vento, sfera in testa, gradi al centro."""
    u = cv.u
    side = min(box.w, box.h)
    lw = max(2, round(3 * u))
    dot = max(2.0, 3.2 * u)
    r = side / 2 - dot
    cx, cy = box.x + box.w / 2, box.y + box.h / 2
    ring = Box(round(cx - r), round(cy - r), round(2 * r), round(2 * r))
    cv.ring(ring, (deg % 360) / 360, color, lw, dot, cv.mix(color, bg, 0.65), bg)
    cv.d.line((cx, ring.y - lw, cx, ring.y + lw * 2), fill=cv.c[color], width=max(1, lw // 2))  # nord
    f = fit("360°", "grotesk", 500, r * 1.25, r * 0.55)
    cv.text((cx, cy + f.size * 0.35), f"{deg % 360:.0f}°", f, color, "ms")
