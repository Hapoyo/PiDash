"""Schedario: geometria delle linguette e disegno delle cartelle.

Le pagine prima di quella aperta stanno in pila in alto, quelle dopo in pila in basso; la
cartella aperta occupa lo spazio in mezzo, attaccata alla propria linguetta. La stessa geometria
serve al disegno e al tocco.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..layout import Box
from .canvas import Canvas
from .theme import font


def unit(w: int, h: int) -> float:
    """Scala del disegno: 1 = riferimento 960×540."""
    return min(w / 960, h / 540)


@dataclass
class Layout:
    """Rettangoli della pagina: disegno e tocco usano gli stessi."""
    tabs: list[Box]        # linguette visibili (una per pagina), dall'alto in basso
    content: Box           # cartella aperta sotto le linguette


def layout(w: int, h: int, n_pages: int, current: int = 0) -> Layout:
    """Linguette alternate a sinistra e a destra, cartella aperta in mezzo."""
    u = unit(w, h)
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


def inner(lay: Layout, u: float) -> Box:
    """Area utile della cartella aperta, dentro il bordo."""
    return lay.content.inset(round(14 * u))


def _folder(cv: Canvas, box: Box, fill: str, outline: str, lw: int, r: int) -> None:
    """Cartella con i soli angoli superiori arrotondati."""
    cv.d.rounded_rectangle(box.rect, radius=r, fill=cv.c[fill], outline=cv.c[outline], width=lw,
                           corners=(True, True, False, False))


def draw_tabs(cv: Canvas, lay: Layout, names: list[str], current: int) -> None:
    """Cartelle sovrapposte: le linguette sotto passano davanti al collo di quella aperta."""
    u = cv.u
    r = round(16 * u)
    lw = max(1, round(2 * u))
    size = round(12 * u)
    body = lay.content
    neck = lay.tabs[current]

    def label(i: int, active: bool) -> None:
        b = lay.tabs[i]
        col = "cream" if active else "ink"
        pad = round(16 * u)
        cv.text((b.x + pad, b.y + b.h / 2), f"{i + 1:03d}", font("mono", size), col, "lm")
        cv.text((b.right - pad, b.y + b.h / 2), names[i].lower(),
                font("mono", size, 700 if active else 400), col, "rm")

    for i in range(current):  # pila sopra: ogni linguetta copre il fondo della precedente
        b = lay.tabs[i]
        _folder(cv, Box(b.x, b.y, b.w, neck.bottom - b.y), "cream", "line", lw, r)
        label(i, False)
    # cartella aperta: linguetta + corpo attaccato, senza la linea di giunzione
    _folder(cv, Box(neck.x, neck.y, neck.w, neck.h + lw), "panel", "cream", lw, r)
    cv.rect(body, r, "panel", "cream", lw)
    cv.d.rectangle((neck.x + lw, neck.bottom - lw, neck.right - lw - 1, neck.bottom + lw),
                   fill=cv.c["panel"])
    label(current, True)
    num_w = font("mono", size).getlength(f"{current + 1:03d}")
    led = max(3, round(6 * u))
    lx, ly = neck.x + round(16 * u) + num_w + round(8 * u), neck.y + neck.h / 2
    cv.add_fx("led", (lx, ly - led / 2, lx + led, ly + led / 2), "orange", "panel")
    for i in range(current + 1, len(lay.tabs)):  # pila sotto, davanti al bordo del corpo
        b = lay.tabs[i]
        _folder(cv, Box(b.x, b.y, b.w, lay.tabs[-1].bottom - b.y), "cream", "line", lw, r)
        label(i, False)
