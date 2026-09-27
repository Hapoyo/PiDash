"""Renderer dello schedario: pagina base (`render`) e fotogrammi animati (`compose`)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageColor

from ..layout import Box
from ..motion import Fx, Motion, Slot
from . import effects, folders
from .canvas import Canvas
from .pages import HITS, PAGES
from .theme import PALETTE, unit

if TYPE_CHECKING:
    from ..app import App

log = logging.getLogger(__name__)


class CyberRenderer:
    """Schedario a linguette: una cartella per pagina, contenuto nella cartella aperta."""

    def __init__(self, palette: dict[str, str] | None = None) -> None:
        self.c = {k: ImageColor.getrgb(v) for k, v in {**PALETTE, **(palette or {})}.items()}
        # registrati durante `render`: numeri che possono decodificarsi, effetti continui
        self.slots: list[Slot] = []
        self.fx: list[Fx] = []
        self._boot_frame: Image.Image | None = None

    # --- geometria (disegno e tocco) -----------------------------------------
    def layout(self, w: int, h: int, n_pages: int, current: int = 0) -> folders.Layout:
        return folders.layout(w, h, n_pages, current)

    def content_inner(self, app: App) -> Box:
        w, h = app.frame_size()
        return folders.inner(folders.layout(w, h, len(app.pages), app.page_idx), unit(w, h))

    def nav_rows(self, app: App) -> list[Box]:
        w, h = app.frame_size()
        return folders.layout(w, h, len(app.pages), app.page_idx).tabs

    def hit_boxes(self, app: App) -> list[tuple[Box, str]]:
        """Bottoni della pagina aperta (rettangolo, id): stessa geometria del disegno."""
        widget: Any = app.page.widget
        hits = HITS.get(widget.name)
        if hits is None:
            return []
        return hits(self.content_inner(app), widget, unit(*app.frame_size()))

    # --- pagina base -----------------------------------------------------------
    def render(self, app: App, now: datetime) -> Image.Image:
        """Disegna la pagina corrente: schedario + contenuto della cartella aperta."""
        w, h = app.frame_size()
        cv = Canvas(Image.new("RGB", (w, h), self.c["bg"]), self.c, unit(w, h))
        lay = folders.layout(w, h, len(app.pages), app.page_idx)
        folders.draw_tabs(cv, lay, [p.name for p in app.pages], app.page_idx)
        box = folders.inner(lay, cv.u)
        name = app.page.widget.name
        try:
            PAGES.get(name, PAGES["clock"])(cv, box, app, now)
        except Exception:  # una pagina difettosa non deve bloccare il dashboard
            log.exception("errore nella pagina %s", app.page.name)
            cv.label((box.x + box.w / 2, box.y + box.h / 2), f"errore in {name}", "pink", "mm")
        alert = app.alerting()
        if alert:
            effects.alert(cv, w, h, alert[1], app.touch)
        self.slots, self.fx = cv.slots, cv.fx
        return cv.img

    # --- motion graphics -------------------------------------------------------
    def compose(self, base: Image.Image, app: App, motion: Motion, t: float) -> Image.Image:
        """Fotogramma animato: avvio, oppure pagina base + effetti + decodifiche + scansione.

        La pagina base si ridisegna solo quando cambiano i dati; qui si aggiunge soltanto ciò
        che si muove, così ogni fotogramma costa pochi millisecondi anche sul Pi 3.
        """
        w, h = base.size
        u = unit(w, h)
        p = motion.boot_progress(t)
        if p is not None:
            self._boot_frame = effects.boot(w, h, u, self.c, app, p)
            return self._boot_frame
        if self._boot_frame is not None:  # fine dell'avvio: si apre la prima pagina
            motion.page_changed(self._boot_frame, t)
            motion.slots_drawn(self.slots, t)
            self._boot_frame = None
        wipe = motion.wipe_progress(t)
        decodes = motion.active_decodes(t)
        fx = self.fx if motion.ambient and not app.alerting() else []
        if wipe is None and not decodes and not fx:
            return base
        cv = Canvas(base.copy(), self.c, u)
        for e in fx:
            effects.draw_fx(cv, e, t)
        frame_no = int(t * motion.fps)
        for slot, progress, keep in decodes:
            effects.draw_decode(cv, slot, progress, keep, frame_no)
        if wipe is not None and motion.wipe_from is not None:
            return effects.wipe(motion.wipe_from, cv.img, wipe, self.c, u)
        return cv.img
