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
               fill: str = "cream", anchor: str = "la", size: float = 11) -> None:
        self._text(d, xy, s.lower(), font("mono", round(size * u)), fill, anchor)

    def _big(self, d: ImageDraw.ImageDraw, box: Box, s: str, fill: str, weight: int = 500,
             anchor: str = "ls", pos: tuple[float, float] | None = None) -> None:
        f = self._fit(s, "grotesk", weight, box.w, box.h)
        x, y = pos if pos else (box.x, box.bottom)
        self._text(d, (x, y), s, f, fill, anchor)

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
                "system": self._system}.get(name, self._home)
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
        clock: Any = app.widgets.get("clock")
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
        clock_box = Box(b.x, clock_top, b.w, date_y - date_h - gap - clock_top)
        self._big(d, clock_box, now.strftime("%H:%M"), "cream", 500,
                  pos=(b.x + b.w / 2, clock_box.bottom), anchor="ms")
        date = f"{GIORNI[now.weekday()]} {now.day:02d} {MESI[now.month - 1]} {now.year}"
        f = self._fit(date.lower(), "grotesk", 500, b.w, date_h)
        self._text(d, (b.x + b.w / 2, clock_box.bottom + gap), date.lower(), f, "tan", "ma")
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
               foot: str, u: float, r: int, ref: str | None = None) -> None:
        """Pannello con etichetta in alto, numero grande al centro e riga di dettaglio in basso."""
        d.rounded_rectangle(box.rect, radius=r, fill=self.c[fill])
        pad = max(4, round(11 * u))
        lab = font("mono", round(11 * u))
        lab_h = int(lab.size) + max(2, round(3 * u))
        self._text(d, (box.x + pad, box.y + pad), label.lower(), lab, "ink", "la")
        foot_h = (lab_h + max(2, round(3 * u))) if foot else 0
        big = Box(box.x + pad, box.y + pad + lab_h, box.w - 2 * pad,
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
        wx: Any = app.widgets["weather"]
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
        self._panel(d, right, "orange", f"vento {vento_nome(deg).lower()}", f"{kn:.0f} kn",
                    f"{rosa(deg).lower()} · raf {gust:.0f} · f{beaufort(kn)}", u, r)
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
        t: Any = app.widgets["timer"]
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
        al: Any = app.widgets["alarm"]
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

    def _rows(self, d: ImageDraw.ImageDraw, box: Box, rows: list[tuple[str, str]], u: float,
              key_color: str = "tan") -> None:
        """Righe "etichetta … valore" distribuite nello spazio disponibile (quelle che ci stanno)."""
        line_h = max(round(15 * u), round(12 * u) + round(6 * u))
        n = max(1, min(len(rows), box.h // line_h))
        step = box.h / n
        for i, (k, v) in enumerate(rows[:n]):
            y = box.y + i * step + (step - round(12 * u)) / 2
            self._micro(d, (box.x, y), k, u, key_color, "la", 12)
            self._micro(d, (box.right, y), str(v).lower(), u, "cream" if key_color == "tan" else "tan",
                        "ra", 12)

    def _system(self, d: ImageDraw.ImageDraw, b: Box, app: App, now: datetime, u: float) -> None:
        """CPU, RAM e disco in pannelli a colori; host, IP, temperatura e uptime in basso."""
        from .widgets.system import uptime_str
        sysw: Any = app.widgets["system"]
        st, hist = sysw.snapshot()
        r, pad, g = round(20 * u), max(4, round(11 * u)), round(10 * u)
        top = Box(b.x, b.y, b.w, round(b.h * 0.46))
        cells = [("cpu", st.cpu, "orange"), ("ram", st.ram_frac, "cream"), ("disco", st.disk_frac, "tan")]
        cw = (top.w - 2 * g) / 3
        for i, (k, v, col) in enumerate(cells):
            cb = Box(round(top.x + i * (cw + g)), top.y, round(cw), top.h)
            self._panel(d, cb, col, k, f"{v * 100:.0f}%" if v is not None else "--", "", u, r,
                        ref="100%")
        # storico CPU a barre
        graph = Box(b.x, top.bottom + g, b.w, round(b.h * 0.26))
        d.rounded_rectangle(graph.rect, radius=r, fill=self.c["panel"], outline=self.c["line"],
                            width=max(1, round(2 * u)))
        self._micro(d, (graph.x + pad, graph.y + round(6 * u)), "cpu · storico", u, "tan", "la", 11)
        inner = graph.inset(pad, round(20 * u))
        slots = 48  # larghezza fissa delle colonne: lo storico cresce da sinistra
        vals = hist[-slots:]
        if vals and inner.w > 0 and inner.h > 0:
            bw = inner.w / slots
            for i, v in enumerate(vals):
                hgt = max(1, round(inner.h * max(0.0, min(1.0, v))))
                x = inner.x + i * bw
                d.rectangle((x, inner.bottom - hgt, x + max(1, bw - 1), inner.bottom - 1),
                            fill=self.c["amber"])
        rows = Box(b.x, graph.bottom + g, b.w, b.bottom - graph.bottom - g)
        info = [("host", st.host), ("ip", st.ip or "--"),
                ("temp", f"{st.temp_c:.0f}°C" if st.temp_c else "--"),
                ("uptime", uptime_str(st.uptime_s))]
        self._rows(d, rows, info, u)

    def _alert(self, d: ImageDraw.ImageDraw, w: int, h: int, u: float, msg: str, touch: bool) -> None:
        b = Box(round(w * 0.2), round(h * 0.38), round(w * 0.6), round(h * 0.24))
        d.rounded_rectangle(b.rect, radius=round(24 * u), fill=self.c["pink"], outline=self.c["cream"],
                            width=max(2, round(4 * u)))
        self._big(d, b.inset(round(20 * u), round(24 * u)), msg.lower(), "paper", 600,
                  pos=(b.x + b.w / 2, b.y + b.h * 0.62), anchor="ms")
        self._micro(d, (b.x + b.w / 2, b.bottom - round(18 * u)),
                    "tocca lo schermo" if touch else "premi a", u, "paper", "mm")

