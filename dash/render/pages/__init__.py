"""Una pagina per tipo di widget: `draw(cv, box, app, now)` disegna il contenuto della cartella.

Per una pagina nuova: un modulo qui con la sua `draw` e una voce in `PAGES`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from . import alarm, home, new, system, timer, weather

if TYPE_CHECKING:
    from datetime import datetime

    from ...app import App
    from ...layout import Box
    from ..canvas import Canvas

    PageDraw = Callable[[Canvas, Box, App, datetime], None]

PAGES: dict[str, PageDraw] = {
    "clock": home.draw,
    "weather": weather.draw,
    "timer": timer.draw,
    "alarm": alarm.draw,
    "system": system.draw,
    "new": new.draw,
}

__all__ = ["PAGES", "new"]
