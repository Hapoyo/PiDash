"""Schedario: geometria delle linguette e disegno delle cartelle.

Le pagine prima di quella aperta stanno in pila in alto, quelle dopo in pila in basso; la
cartella aperta occupa lo spazio in mezzo, attaccata alla propria linguetta. La stessa geometria
serve al disegno e al tocco.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..layout import Box
from .canvas import Canvas
from .theme import GRID, px, unit

TAB_BAND = 0.36  # quota dell'altezza per tutte le linguette insieme (fra tab_min e tab_max)
TAB_WIDTH = 0.66


@dataclass
class Layout:
    """Rettangoli della pagina: disegno e tocco usano gli stessi."""
    tabs: list[Box]        # linguette visibili (una per pagina), dall'alto in basso
    content: Box           # cartella aperta sotto le linguette


def layout(w: int, h: int, n_pages: int, current: int = 0) -> Layout:
    """Linguette alternate a sinistra e a destra, cartella aperta in mezzo."""
    u = unit(w, h)
    m = px(GRID.margin, u)
    n = max(1, n_pages)
    cur = max(0, min(n - 1, current))
    row = max(px(GRID.tab_min, u), min(px(GRID.tab_max, u), round(h * TAB_BAND / n)))
    tab_w = round(w * TAB_WIDTH)

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
    return lay.content.inset(px(GRID.pad, u))


def _folder(cv: Canvas, box: Box, fill: str, outline: str) -> None:
    """Cartella con i soli angoli superiori arrotondati."""
    cv.d.rounded_rectangle(box.rect, radius=cv.radius, fill=cv.c[fill], outline=cv.c[outline],
                           width=cv.line, corners=(True, True, False, False))


SETTINGS = "impostazioni"  # testo della linguetta della scheda "new", accanto all'ingranaggio


def draw_tabs(cv: Canvas, lay: Layout, names: list[str], current: int,
              kinds: list[str] | None = None, warn: str = "") -> None:
    """Cartelle sovrapposte: le linguette sotto passano davanti al collo di quella aperta.

    `warn` sostituisce, in rosa, la parola della linguetta delle Impostazioni (tensione bassa).
    """
    lw = cv.line
    body = lay.content
    neck = lay.tabs[current]
    side = cv.px(10)  # margine orizzontale del testo nella linguetta
    kinds = kinds or [""] * len(names)

    def label(i: int, active: bool) -> None:
        b = lay.tabs[i]
        col = "cream" if active else "ink"
        cy = b.y + b.h / 2
        cv.label((b.x + side, cy), f"{i + 1:03d}", col, "lm")
        if kinds[i] != "new":
            cv.label((b.right - side, cy), names[i], col, "rm", bold=active)
            return
        # Impostazioni: ingranaggio a destra, la parola accanto
        r = b.h * 0.34
        gx = b.right - side - r
        cv.gear((gx, cy), r, "pink" if warn else col, "panel" if active else "cream")
        cv.label((gx - r - cv.px(6), cy), warn or SETTINGS, "pink" if warn else col, "rm",
                 bold=active or bool(warn))

    for i in range(current):  # pila sopra: ogni linguetta copre il fondo della precedente
        b = lay.tabs[i]
        _folder(cv, Box(b.x, b.y, b.w, neck.bottom - b.y), "cream", "line")
        label(i, False)
    # cartella aperta: linguetta + corpo attaccato, senza la linea di giunzione
    _folder(cv, Box(neck.x, neck.y, neck.w, neck.h + lw), "panel", "cream")
    cv.rect(body, "panel", "cream")
    cv.d.rectangle((neck.x + lw, neck.bottom - lw, neck.right - lw - 1, neck.bottom + lw),
                   fill=cv.c["panel"])
    label(current, True)
    led = cv.px(5)
    lx = neck.x + side + cv.f_label.getlength(f"{current + 1:03d}") + cv.px(6)
    ly = neck.y + neck.h / 2
    cv.add_fx("led", (lx, ly - led / 2, lx + led, ly + led / 2), "orange", "panel")
    for i in range(current + 1, len(lay.tabs)):  # pila sotto, davanti al bordo del corpo
        b = lay.tabs[i]
        _folder(cv, Box(b.x, b.y, b.w, lay.tabs[-1].bottom - b.y), "cream", "line")
        label(i, False)
