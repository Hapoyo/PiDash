"""Tema "cyber": computer di bordo retro futuristico a colori (Blade Runner / fantascienza anni '80).

Fondo quasi nero, pannelli arrotondati pieni (arancio, ambra, crema, grigio caldo, rosa),
numeri grandi in Space Grotesk, microetichette tecniche in Space Mono, anelli e dettagli a linea
sottile. Le pagine sono cartelle di uno schedario: una linguetta numerata per pagina; la cartella
aperta è attaccata alla propria linguetta. Home e meteo sono composte qui; le altre pagine
riusano i widget 1-bit, ridisegnati in crema su fondo scuro.
"""
from __future__ import annotations

import calendar
import logging
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageColor, ImageDraw, ImageFont

from .layout import GIORNI, MESI, Box

if TYPE_CHECKING:
    from .main import App

log = logging.getLogger(__name__)

PALETTE: dict[str, str] = {
    "bg": "#1d1815",       # fondo
    "panel": "#2a2320",    # pannello scuro
    "cream": "#eee4cd",    # linguette chiuse, testo chiaro
    "paper": "#f6efdf",    # crema più chiaro (testo del riquadro di allarme)
    "tan": "#a59b8c",
    "orange": "#ee7b50",
    "amber": "#f2bb5b",
    "pink": "#e8505b",
    "ink": "#1d1815",      # testo scuro
    "line": "#5b514a",     # linee sottili e anelli spenti
}

FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"
_FONTS: dict[tuple[str, int, int], ImageFont.FreeTypeFont] = {}


def font(kind: str, size: int, weight: int = 500) -> ImageFont.FreeTypeFont:
    """kind: "grotesk" (variabile 300–700) o "mono" (Space Mono regular/bold)."""
    size = max(8 if kind == "mono" else 6, int(size))  # microetichette leggibili anche a 480×320
    key = (kind, size, weight)
    if key not in _FONTS:
        try:
            if kind == "grotesk":
                f = ImageFont.truetype(str(FONT_DIR / "SpaceGrotesk.ttf"), size)
                try:
                    f.set_variation_by_axes([max(300, min(700, weight))])
                except (OSError, ValueError):
                    pass
            else:
                name = "SpaceMono-Bold.ttf" if weight >= 600 else "SpaceMono-Regular.ttf"
                f = ImageFont.truetype(str(FONT_DIR / name), size)
        except OSError:
            log.warning("font %s non trovato, uso quello di Pillow", kind)
            f = ImageFont.load_default(size)  # type: ignore[assignment]
        _FONTS[key] = f
    return _FONTS[key]


@dataclass
class Layout:
    """Rettangoli della pagina: disegno e tocco usano gli stessi."""
    tabs: list[Box]        # linguette visibili (una per pagina), dall'alto in basso
    content: Box           # cartella aperta sotto le linguette


class CyberRenderer:
    """Schedario a linguette: una cartella per pagina, contenuto nella cartella aperta."""

    def __init__(self, palette: dict[str, str] | None = None) -> None:
        self.c = {k: ImageColor.getrgb(v) for k, v in {**PALETTE, **(palette or {})}.items()}

    # --- geometria ---------------------------------------------------------
    @staticmethod
    def _u(w: int, h: int) -> float:
        return min(w / 960, h / 540)

    def layout(self, w: int, h: int, n_pages: int, current: int = 0) -> Layout:
        """Cartelle di uno schedario: le pagine prima della corrente in pila sopra, quelle dopo in
        pila sotto; la cartella aperta occupa tutto lo spazio in mezzo, attaccata alla sua linguetta."""
        u = self._u(w, h)
        m = round(12 * u)
        n = max(1, n_pages)
        cur = max(0, min(n - 1, current))
        band = h * (0.34 if n > 4 else 0.26)          # spazio complessivo delle linguette
        row = max(round(15 * u), min(round(30 * u), round(band / n)))
        tab_w = round(w * 0.66)

        def x_of(i: int) -> int:
            return m if i % 2 == 0 else w - m - tab_w

        tabs = [Box(x_of(i), m + i * row, tab_w, row) for i in range(cur + 1)]
        below = n - 1 - cur
        for j in range(below):                        # pila in basso, ultima pagina sul bordo
            y = h - m - (below - j) * row
            tabs.append(Box(x_of(cur + 1 + j), y, tab_w, row))
        body_top = tabs[cur].bottom
        body_bottom = (tabs[cur + 1].y if below else h - m)
        return Layout(tabs=tabs, content=Box(m, body_top, w - 2 * m, body_bottom - body_top))

    def content_inner(self, app: App) -> Box:
        w, h = app.frame_size()
        lay = self.layout(w, h, len(app.pages), app.page_idx)
        return lay.content.inset(round(14 * self._u(w, h)))

    def nav_rows(self, app: App) -> list[Box]:
        w, h = app.frame_size()
        return self.layout(w, h, len(app.pages), app.page_idx).tabs

    def _text(self, d: ImageDraw.ImageDraw, xy: tuple[float, float], s: str, f: Any,
              fill: str, anchor: str = "la") -> None:
        d.text(xy, s, font=f, fill=self.c[fill], anchor=anchor)

    @staticmethod
    def _fit(s: str, kind: str, weight: int, max_w: float, max_h: float) -> ImageFont.FreeTypeFont:
        lo, hi = 6, max(6, int(max_h * 1.4))
        while lo < hi:
            mid = (lo + hi + 1) // 2
            l, t, r, b = font(kind, mid, weight).getbbox(s, anchor="ls")
            if r - l <= max_w and b - t <= max_h:
                lo = mid
            else:
                hi = mid - 1
        return font(kind, lo, weight)

    def _micro(self, d: ImageDraw.ImageDraw, xy: tuple[float, float], s: str, u: float,
               fill: str = "cream", anchor: str = "la", size: float = 11,
               lower: bool = True) -> None:
        """`lower=False` dove il maiuscolo è significativo (kB/s, °C)."""
        self._text(d, xy, s.lower() if lower else s, font("mono", round(size * u)), fill, anchor)

    def _big(self, d: ImageDraw.ImageDraw, box: Box, s: str, fill: str, weight: int = 500,
             anchor: str = "ls", pos: tuple[float, float] | None = None) -> None:
        f = self._fit(s, "grotesk", weight, box.w, box.h)
        x, y = pos if pos else (box.x, box.bottom)
        self._text(d, (x, y), s, f, fill, anchor)

    def _ring(self, d: ImageDraw.ImageDraw, box: Box, frac: float, color: str, lw: int,
              dot: float) -> None:
        """Anello spento + arco acceso da ore 12 in senso orario, con una sfera in testa."""
        d.ellipse(box.rect, outline=self.c["line"], width=lw)
        ang = -90 + 360 * max(0.0, min(1.0, frac))
        if frac > 0:
            d.arc(box.rect, -90, ang, fill=self.c[color], width=lw)
        cx, cy = box.x + box.w / 2, box.y + box.h / 2
        rad = math.radians(ang)
        px, py = cx + (box.w / 2) * math.cos(rad), cy + (box.h / 2) * math.sin(rad)
        d.ellipse((px - dot, py - dot, px + dot, py + dot), fill=self.c[color])

    def _cycles(self, d: ImageDraw.ImageDraw, box: Box, cycles: dict[str, float], u: float) -> None:
        """Tre anelli concentrici con una sfera ciascuno: settimana, mese, anno."""
        lw = max(2, round(3 * u))
        dot = max(2.0, 3.2 * u)
        leg_h = round(13 * u)
        side = min(box.w, box.h - leg_h)
        cx, cy = box.x + box.w / 2, box.y + (box.h - leg_h) / 2
        anelli = (("anno", "orange"), ("mese", "amber"), ("settimana", "cream"))
        for i, (key, col) in enumerate(anelli):
            r = side / 2 - dot - i * (lw + max(4, round(6 * u)))
            if r <= lw:
                continue
            self._ring(d, Box(round(cx - r), round(cy - r), round(2 * r), round(2 * r)),
                       cycles.get(key, 0.0), col, lw, dot)
        # legenda: tre sigle nei colori dei rispettivi anelli
        sigle = [(k[:3], c) for k, c in reversed(anelli)]
        f = font("mono", round(11 * u))
        widths = [f.getlength(s + " ") for s, _ in sigle]
        x = cx - sum(widths) / 2
        for (s, col), wdt in zip(sigle, widths):
            self._text(d, (x, box.bottom - leg_h), s, f, col, "la")
            x += wdt

    def _compass(self, d: ImageDraw.ImageDraw, box: Box, deg: float, u: float,
                 fg: str = "ink", dim: str = "paper") -> None:
        """Rosa dei venti: freccia nella direzione da cui soffia il vento (uso nautico)."""
        side = min(box.w, box.h)
        cx, cy = box.x + box.w / 2, box.y + box.h / 2
        r = side / 2
        lw = max(1, round(2 * u))
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=self.c[dim], width=lw)
        f = font("mono", max(7, round(9 * u)))
        for i, s in enumerate(("n", "e", "s", "o")):  # quattro punti cardinali
            a = math.radians(-90 + 90 * i)
            self._text(d, (cx + (r - 6 * u) * math.cos(a), cy + (r - 6 * u) * math.sin(a)),
                       s, f, fg if s == "n" else dim, "mm")
        for i in range(8):  # tacche intermedie
            a = math.radians(45 * i + 22.5)
            d.line((cx + (r - 2 * u) * math.cos(a), cy + (r - 2 * u) * math.sin(a),
                    cx + r * math.cos(a), cy + r * math.sin(a)), fill=self.c[dim], width=lw)
        # riga dal centro al bordo, verso la parte da cui soffia il vento (0° = da nord)
        a = math.radians(deg - 90)
        tip = r - 7 * u
        px, py = cx + tip * math.cos(a), cy + tip * math.sin(a)
        bar = max(4, round(6 * u))
        d.line((cx, cy, px, py), fill=self.c[fg], width=bar)
        for ex, ey in ((cx, cy), (px, py)):  # estremi arrotondati come le barre delle altre pagine
            d.ellipse((ex - bar / 2, ey - bar / 2, ex + bar / 2, ey + bar / 2), fill=self.c[fg])

    # --- schedario ---------------------------------------------------------
    def _folder(self, d: ImageDraw.ImageDraw, box: Box, fill: str, outline: str, lw: int,
                r: int, top_only: bool = True) -> None:
        d.rounded_rectangle(box.rect, radius=r, fill=self.c[fill], outline=self.c[outline],
                            width=lw, corners=(True, True, not top_only, not top_only))

    def _tabs(self, d: ImageDraw.ImageDraw, lay: Layout, names: list[str], current: int,
              u: float) -> None:
        """Cartelle sovrapposte: le linguette sotto passano davanti al collo di quella aperta."""
        r = round(16 * u)
        lw = max(1, round(2 * u))
        size = round(12 * u)
        body = lay.content
        neck = lay.tabs[current]

        def label(i: int, active: bool) -> None:
            b = lay.tabs[i]
            col = "cream" if active else "ink"
            pad = round(16 * u)
            self._text(d, (b.x + pad, b.y + b.h / 2), f"{i + 1:03d}", font("mono", size), col, "lm")
            self._text(d, (b.right - pad, b.y + b.h / 2), names[i].lower(),
                       font("mono", size, 700 if active else 400), col, "rm")

        for i in range(current):  # pila sopra: ogni linguetta copre il fondo della precedente
            b = lay.tabs[i]
            self._folder(d, Box(b.x, b.y, b.w, neck.bottom - b.y), "cream", "line", lw, r)
            label(i, False)
        # cartella aperta: linguetta + corpo attaccato, senza la linea di giunzione
        self._folder(d, Box(neck.x, neck.y, neck.w, neck.h + lw), "panel", "cream", lw, r)
        d.rounded_rectangle(body.rect, radius=r, fill=self.c["panel"], outline=self.c["cream"],
                            width=lw)
        d.rectangle((neck.x + lw, neck.bottom - lw, neck.right - lw - 1, neck.bottom + lw),
                    fill=self.c["panel"])
        label(current, True)
        for i in range(current + 1, len(lay.tabs)):  # pila sotto, davanti al bordo del corpo
            b = lay.tabs[i]
            self._folder(d, Box(b.x, b.y, b.w, lay.tabs[-1].bottom - b.y), "cream", "line", lw, r)
            label(i, False)

    def render(self, app: App, now: datetime) -> Image.Image:
        """Disegna la pagina corrente: schedario + contenuto della cartella aperta."""
        w, h = app.frame_size()
        u = self._u(w, h)
        img = Image.new("RGB", (w, h), self.c["bg"])
        d = ImageDraw.Draw(img)
        lay = self.layout(w, h, len(app.pages), app.page_idx)
        self._tabs(d, lay, [p.name for p in app.pages], app.page_idx, u)
        inner = lay.content.inset(round(14 * u))
        name = app.page.widget.name
        page = {"weather": self._weather, "timer": self._timer, "alarm": self._alarm,
                "system": self._system, "new": self._new}.get(name, self._home)
        try:
            page(d, inner, app, now, u)
        except Exception:  # una pagina difettosa non deve bloccare il dashboard
            log.exception("errore nella pagina %s", app.page.name)
            self._micro(d, (inner.x + inner.w / 2, inner.y + inner.h / 2),
                        f"errore in {name}", u, "pink", "mm", 13)
        alert = app.alerting()
        if alert:
            self._alert(d, w, h, u, alert[1], app.touch)
        return img

    # --- contenuti nativi ----------------------------------------------------
    def _home(self, d: ImageDraw.ImageDraw, b: Box, app: App, now: datetime, u: float) -> None:
        """Ora, data, luogo, alba/tramonto, avanzamento della giornata, settimana e giorno dell'anno."""
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
        self._micro(d, (head.x, head.y), f"loc // {name or 'n/d'}", u, "cream", "la", 12)
        self._micro(d, (head.right, head.y), f"{lat:.3f}n {lon:.3f}e", u, "tan", "ra", 12)
        clock_top = head.bottom + round(6 * u)
        gap = max(4, round(8 * u))
        band = Box(b.x, clock_top, b.w, date_y - date_h - gap - clock_top)
        # anello dei cicli a destra, ora a sinistra nello spazio che resta
        side = min(band.h + date_h, round(b.w * 0.30))
        clock_box = Box(band.x, band.y, band.w - side - gap, band.h)
        self._big(d, clock_box, now.strftime("%H:%M"), "cream", 500,
                  pos=(clock_box.x + clock_box.w / 2, clock_box.bottom), anchor="ms")
        if clock is not None and side > round(28 * u):
            ring = Box(band.right - side, band.y + (band.h + date_h - side) // 2, side, side)
            self._cycles(d, ring, clock.cycles(now), u)
        date = f"{GIORNI[now.weekday()]} {now.day:02d} {MESI[now.month - 1]} {now.year}"
        f = self._fit(date.lower(), "grotesk", 500, clock_box.w, date_h)
        self._text(d, (clock_box.x + clock_box.w / 2, clock_box.bottom + gap), date.lower(),
                   f, "tan", "ma")
        label, frac = clock.progress(now) if clock is not None else ("GIORNO", 0.0)
        d.rounded_rectangle(bar.rect, radius=bar.h // 2, fill=self.c["line"])
        d.rounded_rectangle((bar.x, bar.y, bar.x + max(bar.h, round(bar.w * frac)), bar.bottom - 1),
                            radius=bar.h // 2, fill=self.c["orange"])
        sun = clock.sun(now) if clock is not None else None
        yday = now.timetuple().tm_yday
        in_year = 366 if calendar.isleap(now.year) else 365
        rows = [(f"{label.lower()} {frac * 100:.0f}%",
                 f"alba {sun[0] if sun else '--:--'} · tramonto {sun[1] if sun else '--:--'}"),
                (f"settimana n:{now.isocalendar().week:02d}", f"giorno {yday}/{in_year}")]
        for i, (left, right) in enumerate(rows):
            y = rows_y + i * line
            self._micro(d, (b.x, y), left, u, "orange" if i == 0 else "tan", "la", 12)
            self._micro(d, (b.right, y), right, u, "cream", "ra", 12)

    def _panel(self, d: ImageDraw.ImageDraw, box: Box, fill: str, label: str, value: str,
               foot: str, u: float, r: int, ref: str | None = None, reserve: int = 0) -> None:
        """Pannello con etichetta in alto, numero grande al centro e riga di dettaglio in basso.

        `reserve`: larghezza lasciata libera a destra del numero (bussola del vento).
        """
        d.rounded_rectangle(box.rect, radius=r, fill=self.c[fill])
        pad = max(4, round(11 * u))
        lab = font("mono", round(11 * u))
        lab_h = int(lab.size) + max(2, round(3 * u))
        self._text(d, (box.x + pad, box.y + pad), label.lower(), lab, "ink", "la")
        foot_h = (lab_h + max(2, round(3 * u))) if foot else 0
        big = Box(box.x + pad, box.y + pad + lab_h, box.w - 2 * pad - reserve,
                  box.h - 2 * pad - lab_h - foot_h)
        if big.h > round(10 * u):
            # `ref` dà la taglia (numeri della stessa serie allineati, es. 7% e 100%)
            f = self._fit(ref or value, "grotesk", 500, big.w, big.h)
            self._text(d, (big.x, big.bottom), value, f, "ink", "ls")
        if foot:
            self._text(d, (box.right - pad, box.bottom - pad), foot.lower(), lab, "ink", "rd")

    def _weather(self, d: ImageDraw.ImageDraw, b: Box, app: App, now: datetime, u: float) -> None:
        """Pagina meteo unica: stato attuale, vento, valori, previsione oraria, sole e luna."""
        from .widgets.weather import (SHORT, beaufort, describe, moon_illumination, moon_name,
                                      moon_phase, rosa, vento_nome)
        wx: Any = app.page.widget
        data = wx.snapshot()
        if not data:
            self._micro(d, (b.x + b.w / 2, b.y + b.h / 2), "meteo in attesa di dati...", u, "tan", "mm", 13)
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
        self._panel(d, left, "cream", SHORT.get(text, text),
                    f"{float(cur.get('temperature_2m', 0)):.0f}°",
                    f"percepita {float(cur.get('apparent_temperature', 0)):.0f}°", u, r)
        pad = max(4, round(11 * u))
        band_y = right.y + pad + round(16 * u)            # sotto l'etichetta
        band_h = right.h - (band_y - right.y) - pad - round(22 * u)  # sopra la riga di dettaglio
        comp = min(band_h, round(right.w * 0.34))
        mostra = comp > round(26 * u)
        self._panel(d, right, "orange", f"vento {vento_nome(deg).lower()} {deg:.0f}°", f"{kn:.0f} kn",
                    f"{rosa(deg).lower()} · raf {gust:.0f} · f{beaufort(kn)}", u, r,
                    reserve=comp + pad if mostra else 0)
        if mostra:
            self._compass(d, Box(right.right - pad - comp, band_y + (band_h - comp) // 2,
                                 comp, comp), deg, u)
        # riga 2: tre valori
        mid_h = round(b.h * 0.16)
        mid = Box(b.x, top_h + b.y + g, b.w, mid_h)
        cw = (mid.w - 2 * g) / 3
        cells = [("pioggia", f"{rain:.0f}%", "pink"),
                 ("umidità", f"{cur.get('relative_humidity_2m', 0):.0f}%", "tan"),
                 ("pressione", f"{cur.get('pressure_msl', 0):.0f}", "amber")]
        for i, (k, v, col) in enumerate(cells):
            cb = Box(round(mid.x + i * (cw + g)), mid.y, round(cw), mid.h)
            self._panel(d, cb, col, k, v, "", u, r, ref="1013")
        # riga 3: previsione oraria
        fc_top = mid.bottom + g
        foot_h = round(20 * u)
        fc = Box(b.x, fc_top, b.w, b.bottom - fc_top - foot_h - g)
        d.rounded_rectangle(fc.rect, radius=r, fill=self.c["panel"], outline=self.c["line"],
                            width=max(1, round(2 * u)))
        times: list[str] = data.get("hourly", {}).get("time", [])
        steps = [n for n in (3, 6, 9, 12, 15) if idx + n < len(times)]
        cw = fc.w / max(1, len(steps))
        for i, n in enumerate(steps):
            x = fc.x + i * cw
            t = wx.hourly(data, "temperature_2m", idx + n)
            kn2 = wx.hourly(data, "wind_speed_10m", idx + n) or 0
            p = wx.hourly(data, "precipitation_probability", idx + n) or 0
            self._micro(d, (x + cw / 2, fc.y + round(8 * u)), f"{times[idx + n][11:13]}h", u, "tan", "ma", 11)
            self._text(d, (x + cw / 2, fc.y + fc.h * 0.62), f"{t:.0f}°" if t is not None else "--",
                       font("grotesk", round(fc.h * 0.34), 500), "cream", "ms")
            self._micro(d, (x + cw / 2, fc.bottom - round(8 * u)), f"{kn2:.0f}kn · {p:.0f}%", u, "amber", "md", 11)
            if i:
                d.line((x, fc.y + round(8 * u), x, fc.bottom - round(8 * u)), fill=self.c["line"])
        # riga 4: sole e luna
        phase = moon_phase(now)
        sunrise, sunset = str(wx.daily(data, "sunrise") or "")[-5:], str(wx.daily(data, "sunset") or "")[-5:]
        self._micro(d, (b.x, b.bottom - round(6 * u)), f"alba {sunrise} · tramonto {sunset}",
                    u, "cream", "ld", 12)
        self._micro(d, (b.right, b.bottom - round(6 * u)),
                    f"luna {moon_name(phase).lower()} {moon_illumination(phase) * 100:.0f}%",
                    u, "tan", "rd", 12)

    def _timer(self, d: ImageDraw.ImageDraw, b: Box, app: App, now: datetime, u: float) -> None:
        """Conto alla rovescia grande, barra del tempo residuo e preset selezionabili."""
        from .widgets.timer import TimerState
        t: Any = app.page.widget
        secs = t.shown_remaining()
        mm, ss = divmod(secs, 60)
        r, pad, g = round(20 * u), max(4, round(11 * u)), round(10 * u)
        running = t.state is TimerState.RUNNING
        top = Box(b.x, b.y, b.w, round(b.h * 0.58))
        d.rounded_rectangle(top.rect, radius=r, fill=self.c["orange" if running else "cream"])
        self._micro(d, (top.x + pad, top.y + pad), t.label(), u, "ink", "la", 12)
        self._micro(d, (top.right - pad, top.y + pad), t.state.value.lower(), u, "ink", "ra", 12)
        num = Box(top.x + pad, top.y + pad + round(14 * u), top.w - 2 * pad,
                  top.h - 2 * pad - round(14 * u))
        self._big(d, num, f"{mm:02d}:{ss:02d}", "ink", 500,
                  pos=(top.x + top.w / 2, num.bottom), anchor="ms")
        # barra del tempo residuo
        bar = Box(b.x, top.bottom + g, b.w, max(round(10 * u), round(b.h * 0.1)))
        d.rounded_rectangle(bar.rect, radius=bar.h // 2, fill=self.c["panel"], outline=self.c["line"],
                            width=max(1, round(2 * u)))
        frac = t.remaining() / t.duration if t.duration else 0.0
        if frac > 0:
            d.rounded_rectangle((bar.x, bar.y, bar.x + max(bar.h, round(bar.w * frac)), bar.bottom - 1),
                                radius=bar.h // 2, fill=self.c["amber"])
        # preset: quello attivo in evidenza
        row = Box(b.x, bar.bottom + g, b.w, b.bottom - bar.bottom - g)
        n = len(t.presets)
        cw = (row.w - (n - 1) * g) / n
        for i, preset in enumerate(t.presets):
            cb = Box(round(row.x + i * (cw + g)), row.y, round(cw), row.h)
            active = i == t.preset_idx
            d.rounded_rectangle(cb.rect, radius=r, fill=self.c["pink" if active else "panel"],
                                outline=self.c["cream" if active else "line"], width=max(1, round(2 * u)))
            self._text(d, (cb.x + cb.w / 2, cb.y + cb.h / 2), f"{preset // 60}'",
                       font("grotesk", round(cb.h * 0.5), 600), "paper" if active else "cream", "mm")

    def _alarm(self, d: ImageDraw.ImageDraw, b: Box, app: App, now: datetime, u: float) -> None:
        """Prossima sveglia in grande, stato e elenco delle sveglie configurate."""
        al: Any = app.page.widget
        nxt = al.next_alarm(now) if al.armed else None
        r, pad, g = round(20 * u), max(4, round(11 * u)), round(10 * u)
        top = Box(b.x, b.y, b.w, round(b.h * 0.52))
        armed = al.armed and nxt is not None
        d.rounded_rectangle(top.rect, radius=r, fill=self.c["cream" if armed else "panel"],
                            outline=self.c["cream"], width=0 if armed else max(1, round(2 * u)))
        col = "ink" if armed else "cream"
        self._text(d, (top.x + pad, top.y + pad), "sveglia", font("mono", round(12 * u)), col, "la")
        self._text(d, (top.right - pad, top.y + pad), "armata" if armed else "disarmata",
                   font("mono", round(12 * u), 700), col, "ra")
        first = nxt[0] if nxt else (al.alarms[0] if al.alarms else None)
        text = f"{first.hour:02d}:{first.minute:02d}" if first else "--:--"
        num = Box(top.x + pad, top.y + pad + round(14 * u), top.w - 2 * pad,
                  top.h - 2 * pad - round(14 * u))
        self._big(d, num, text, col, 500, pos=(top.x + top.w / 2, num.bottom), anchor="ms")
        rows = Box(b.x, top.bottom + g, b.w, b.bottom - top.bottom - g)
        if nxt:
            delta = nxt[1] - now
            hh, mm = divmod(int(delta.total_seconds()) // 60, 60)
            head = Box(rows.x, rows.y, rows.w, round(rows.h * 0.42))
            d.rounded_rectangle(head.rect, radius=r, fill=self.c["amber"])
            self._micro(d, (head.x + pad, head.y + round(6 * u)), "prossima", u, "ink", "la", 11)
            line = f"{GIORNI[nxt[1].weekday()].lower()} · tra {hh}h{mm:02d}"
            self._text(d, (head.right - pad, head.bottom - round(8 * u)), line,
                       font("grotesk", round(head.h * 0.42), 500), "ink", "rd")
            rows = Box(rows.x, head.bottom + g, rows.w, rows.bottom - head.bottom - g)
        lines = [(f"#{i + 1} {a.hour:02d}:{a.minute:02d} · {'on' if a.enabled else 'off'}",
                  a.label_days()) for i, a in enumerate(al.alarms)]
        self._rows(d, rows, lines, u, key_color="cream")

    @staticmethod
    def chips(box: Box, n: int, u: float, per_row: int = 0) -> list[Box]:
        """Riquadri del catalogo della scheda "+": stessa geometria per disegno e tocco."""
        if n <= 0:
            return []
        per_row = per_row or min(3, n)
        g = round(10 * u)
        rows = max(1, -(-n // per_row))
        cw = (box.w - (per_row - 1) * g) / per_row
        ch = min((box.h - (rows - 1) * g) / rows, 90 * u)  # riquadri alti al massimo come un tasto
        return [Box(round(box.x + (i % per_row) * (cw + g)), round(box.y + (i // per_row) * (ch + g)),
                    round(cw), round(ch)) for i in range(n)]

    def select_boxes(self, app: App) -> list[Box]:
        """Riquadri selezionabili col tocco nella pagina aperta (solo la scheda "+")."""
        widget: Any = app.page.widget
        if widget.name != "new":
            return []
        b = self.content_inner(app)
        u = self._u(*app.frame_size())
        return self.chips(self._new_grid(b, u), len(widget.voci()), u)

    @staticmethod
    def _new_grid(b: Box, u: float) -> Box:
        """Zona del catalogo: sotto il riquadro con il "+"."""
        top_h = round(b.h * 0.34)
        g = round(10 * u)
        return Box(b.x, b.y + top_h + g, b.w, b.h - top_h - g)

    def _new(self, d: ImageDraw.ImageDraw, b: Box, app: App, now: datetime, u: float) -> None:
        """Catalogo delle schede: "+" grande in testa, voci sotto; A crea, B cambia voce."""
        widget: Any = app.page.widget
        voci = widget.voci()
        scelta = widget.scelta()
        r, pad, g = round(20 * u), max(4, round(11 * u)), round(10 * u)
        top = Box(b.x, b.y, b.w, round(b.h * 0.34))
        d.rounded_rectangle(top.rect, radius=r, fill=self.c["cream"])
        self._micro(d, (top.x + pad, top.y + pad), "schede da aggiungere", u, "ink", "la", 12)
        self._micro(d, (top.right - pad, top.y + pad),
                    "tocca il + per confermare" if app.touch else "a conferma · b scegli",
                    u, "ink", "ra", 11)
        num = Box(top.x + pad, top.y + pad + round(14 * u), round(top.h * 0.7),
                  top.h - 2 * pad - round(14 * u))
        self._big(d, num, "+", "ink", 600, pos=(top.x + pad + num.w / 2, num.bottom), anchor="ms")
        if scelta is not None:
            azione = "aggiungi" if scelta.azione == "add" else "togli"  # la voce fa da interruttore
            f = self._fit(f"{azione} {scelta.label}", "grotesk", 500, top.w - num.w - 3 * pad,
                          num.h * 0.62)
            self._text(d, (top.right - pad, num.bottom), f"{azione} {scelta.label}", f, "ink", "rs")
        grid = self._new_grid(b, u)
        riquadri = self.chips(grid, len(voci), u)
        if riquadri:  # sotto i riquadri: come funziona l'interruttore
            self._micro(d, (b.x + b.w / 2, riquadri[-1].bottom + round(14 * u)),
                        "la stessa voce toglie la scheda quando è già nello schedario",
                        u, "tan", "ma", 11)
        for i, (voce, cb) in enumerate(zip(voci, riquadri)):
            active = scelta is not None and i == widget.idx % len(voci)
            togli = voce.azione == "del"
            fill = "pink" if active else "panel"
            d.rounded_rectangle(cb.rect, radius=r, fill=self.c[fill],
                                outline=self.c["cream" if active else "line"],
                                width=max(1, round(2 * u)))
            col = "paper" if active else ("tan" if togli else "cream")
            self._text(d, (cb.x + cb.w / 2, cb.y + cb.h / 2 - round(3 * u)),
                       ("− " if togli else "+ ") + voce.label,
                       self._fit(f"− {voce.label}", "grotesk", 600, cb.w - round(12 * u), cb.h * 0.42),
                       col, "mm")

    def _rows(self, d: ImageDraw.ImageDraw, box: Box, rows: list[tuple[str, str]], u: float,
              key_color: str = "tan", lower: bool = True) -> None:
        """Righe "etichetta … valore" distribuite nello spazio disponibile (quelle che ci stanno)."""
        line_h = max(round(15 * u), round(12 * u) + round(6 * u))
        n = max(1, min(len(rows), box.h // line_h))
        step = box.h / n
        for i, (k, v) in enumerate(rows[:n]):
            y = box.y + i * step + (step - round(12 * u)) / 2
            self._micro(d, (box.x, y), k, u, key_color, "la", 12)
            self._micro(d, (box.right, y), str(v), u, "cream" if key_color == "tan" else "tan",
                        "ra", 12, lower=lower)

    def _system(self, d: ImageDraw.ImageDraw, b: Box, app: App, now: datetime, u: float) -> None:
        """CPU, RAM e disco in pannelli a colori; host, IP, temperatura e uptime in basso."""
        from .widgets.system import rate_str, uptime_str
        sysw: Any = app.page.widget
        st, hist = sysw.snapshot()
        r, pad, g = round(20 * u), max(4, round(11 * u)), round(10 * u)
        top = Box(b.x, b.y, b.w, round(b.h * 0.46))
        cells = [("cpu", st.cpu, "orange"), ("ram", st.ram_frac, "cream"), ("disco", st.disk_frac, "tan")]
        cw = (top.w - 2 * g) / 3
        for i, (k, v, col) in enumerate(cells):
            cb = Box(round(top.x + i * (cw + g)), top.y, round(cw), top.h)
            self._panel(d, cb, col, k, f"{v * 100:.0f}%" if v is not None else "--", "", u, r,
                        ref="100%")
        # storici affiancati: cpu in percentuale, rete in scala sul massimo mostrato
        net = sysw.net_snapshot() if hasattr(sysw, "net_snapshot") else []
        gh = round(b.h * 0.26)
        gw = (b.w - g) / 2
        cpu_box = Box(b.x, top.bottom + g, round(gw), gh)
        net_box = Box(round(b.x + gw + g), top.bottom + g, round(gw), gh)
        picco = max(net) if net else 0.0
        self._graph(d, cpu_box, hist, 1.0, "cpu · storico", "amber", u, r, pad)
        self._graph(d, net_box, net, picco, f"rete · picco {rate_str(picco)}", "orange", u, r, pad)
        rows = Box(b.x, cpu_box.bottom + g, b.w, b.bottom - cpu_box.bottom - g)
        info = [("host", st.host), ("ip", st.ip or "--"),
                ("rete", f"giù {rate_str(st.net_rx)} · su {rate_str(st.net_tx)}"),
                ("temp", f"{st.temp_c:.0f}°C" if st.temp_c else "--"),
                ("uptime", uptime_str(st.uptime_s))]
        self._rows(d, rows, info, u, lower=False)

    def _graph(self, d: ImageDraw.ImageDraw, box: Box, vals: list[float], top: float, label: str,
               color: str, u: float, r: int, pad: int) -> None:
        """Istogramma a colonne di larghezza fissa: lo storico cresce da sinistra."""
        d.rounded_rectangle(box.rect, radius=r, fill=self.c["panel"], outline=self.c["line"],
                            width=max(1, round(2 * u)))
        self._micro(d, (box.x + pad, box.y + round(6 * u)), label, u, "tan", "la", 11, lower=False)
        inner = box.inset(pad, round(20 * u))
        slots = 48
        vals = vals[-slots:]
        if not vals or top <= 0 or inner.w <= 0 or inner.h <= 0:
            return
        bw = inner.w / slots
        for i, v in enumerate(vals):
            hgt = max(1, round(inner.h * max(0.0, min(1.0, v / top))))
            x = inner.x + i * bw
            d.rectangle((x, inner.bottom - hgt, x + max(1, bw - 1), inner.bottom - 1),
                        fill=self.c[color])

    def _alert(self, d: ImageDraw.ImageDraw, w: int, h: int, u: float, msg: str, touch: bool) -> None:
        b = Box(round(w * 0.2), round(h * 0.38), round(w * 0.6), round(h * 0.24))
        d.rounded_rectangle(b.rect, radius=round(24 * u), fill=self.c["pink"], outline=self.c["cream"],
                            width=max(2, round(4 * u)))
        self._big(d, b.inset(round(20 * u), round(24 * u)), msg.lower(), "paper", 600,
                  pos=(b.x + b.w / 2, b.y + b.h * 0.62), anchor="ms")
        self._micro(d, (b.x + b.w / 2, b.bottom - round(18 * u)),
                    "tocca lo schermo" if touch else "premi a", u, "paper", "mm")

