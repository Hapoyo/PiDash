"""Dashboard in esecuzione: pagine dello schedario, eventi, ciclo di aggiornamento."""
from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image

from .config import save_local
from .display import Display
from .inputs import Buzzer, Event, Tap, panel_to_frame
from .motion import Motion
from .widgets import ETICHETTE, WIDGET_NAMES, Widget, WidgetFactory
from .widgets.new import NewWidget

log = logging.getLogger("dash")

TAP_TOLERANCE = 12  # pixel a 480×320: un tocco appena fuori da un bottone vale per il più vicino


@dataclass
class Page:
    """Una cartella dello schedario: nome sulla linguetta e widget che ne fornisce i dati."""
    name: str
    widget: Widget
    key: str = ""      # identificatore univoco (es. "timer#2"): più pagine dello stesso tipo
    kind: str = ""     # tipo di widget della pagina


class App:
    """Stato del dashboard e ciclo di aggiornamento."""

    def __init__(self, cfg: dict[str, Any], display: Display, events: queue.Queue[Any],
                 config_path: Path | None = None) -> None:
        self.cfg = cfg
        self.display = display
        self.events = events
        self.config_path = config_path  # dove salvare le pagine create dalla scheda "+"
        self.factory = WidgetFactory(cfg)
        self.pages: list[Page] = []
        self.widgets: dict[str, Widget] = {}
        for p in cfg["pages"]:
            self._new_page(p["widget"], p["name"])
        self.page_idx = 0
        self.buzzer = Buzzer(cfg["input"].get("buzzer_pin"), bool(cfg["input"].get("sound")))
        self._stop = threading.Event()
        self.buttons: list[Any] = []  # riferimenti ai pulsanti GPIO (evita il GC)
        self._last_key: Any = None
        self.touch = False  # True se il touchscreen è attivo (cambia il testo dell'allarme)
        self.touch_cal: Any = None  # TouchCalibration in uso, per la calibrazione a schermo
        self._renderer: Any = None
        self.motion = Motion.from_cfg(cfg.get("motion") or {})
        self._base: Image.Image | None = None    # pagina ferma, ridisegnata solo se cambiano i dati
        self._frame: Image.Image | None = None   # ultimo fotogramma mostrato (prima della rotazione)
        self._shown_page = -1
        self._last_fkey: int | None = None

    @property
    def page(self) -> Page:
        return self.pages[self.page_idx]

    # --- pagine ----------------------------------------------------------
    def _new_page(self, kind: str, name: str, at: int | None = None) -> Page:
        """Crea la pagina e il suo widget; `at` la inserisce prima di quella posizione."""
        key, n = kind, 1
        while key in self.widgets:  # chiave libera anche dopo aver tolto pagine dello stesso tipo
            n += 1
            key = f"{kind}#{n}"
        page = Page(name, self.factory.make(kind), key, kind)
        if isinstance(page.widget, NewWidget):  # la scheda "+" agisce sullo schedario
            page.widget.pagine = self.page_kinds
            page.widget.aggiungi = self.add_page
            page.widget.togli = self.remove_page
        self.pages.insert(len(self.pages) if at is None else at, page)
        self.widgets[key] = page.widget
        return page

    def page_kinds(self) -> dict[str, str]:
        """{tipo: chiave} delle pagine presenti, per l'interruttore della scheda "+"."""
        return {p.kind: p.key for p in self.pages if p.kind != "new"}

    def add_page(self, kind: str) -> None:
        """Aggiunge una pagina del tipo indicato prima della scheda "+" e ci si sposta."""
        if kind not in WIDGET_NAMES or kind == "new":
            log.warning("tipo di pagina sconosciuto: %s", kind)
            return
        base = ETICHETTE.get(kind, kind.capitalize())
        nomi = {p.name for p in self.pages}
        name, n = base, 1
        while name in nomi:
            n += 1
            name = f"{base} {n}"
        at = next((i for i, p in enumerate(self.pages) if p.kind == "new"), len(self.pages))
        self._new_page(kind, name, at)
        self.page_idx = at
        self._save_pages()

    def remove_page(self, key: str) -> None:
        """Toglie una pagina creata in precedenza; l'ultima rimasta non si può togliere."""
        idx = next((i for i, p in enumerate(self.pages) if p.key == key), None)
        if idx is None or len(self.pages) <= 1 or self.pages[idx].kind == "new":
            return
        corrente = self.page
        page = self.pages.pop(idx)
        self.widgets.pop(page.key, None)
        page.widget.close()
        # si resta sulla pagina aperta (di norma la scheda "+"), non su quella che ha preso il suo posto
        self.page_idx = next((i for i, p in enumerate(self.pages) if p is corrente),
                             min(self.page_idx, len(self.pages) - 1))
        self._save_pages()

    def _save_pages(self) -> None:
        """Salva lo schedario in config.local.json, così sopravvive al riavvio."""
        self.cfg["pages"] = [{"name": p.name, "widget": p.kind} for p in self.pages]
        if self.config_path is None:
            return
        try:
            save_local(self.config_path, {"pages": self.cfg["pages"]})
        except OSError as exc:
            log.error("pagine non salvate: %s", exc)

    # --- eventi ----------------------------------------------------------
    def alerting(self) -> tuple[Widget, str] | None:
        for w in self.widgets.values():
            msg = w.alert()
            if msg:
                return w, msg
        return None

    def handle(self, ev: Event, now: datetime) -> None:
        if self.motion.boot_start is not None and ev is not Event.QUIT:
            self.motion.skip_boot()  # un tasto durante l'avvio lo salta e basta
            return
        if ev is Event.QUIT:
            self._stop.set()
        elif ev is Event.NEXT:
            self._goto(self.page_idx + 1)
        elif ev in (Event.ACTION, Event.BACK):
            alert = self.alerting()
            target = alert[0] if alert and ev is Event.ACTION else self.page.widget
            (target.on_action if ev is Event.ACTION else target.on_back)(now)

    def frame_size(self) -> tuple[int, int]:
        """Dimensioni del fotogramma disegnato (prima della rotazione verso il pannello)."""
        d = self.cfg["display"]
        return (d["height"], d["width"]) if d["rotate"] in (90, 270) else (d["width"], d["height"])

    @property
    def renderer(self) -> Any:
        if self._renderer is None:
            from .render import CyberRenderer
            self._renderer = CyberRenderer(self.cfg["theme"].get("palette"))
        return self._renderer

    def _goto(self, idx: int) -> None:
        self.page_idx = idx % len(self.pages)

    def handle_tap(self, tap: Tap, now: datetime) -> None:
        """Linguetta → apre quella cartella; bottone → la sua azione; resto → azione del widget."""
        if self.motion.boot_start is not None:
            self.motion.skip_boot()
            return
        fx, fy = panel_to_frame(tap.x, tap.y, self.cfg["display"]["rotate"])
        w, h = self.frame_size()
        px, py = fx * w, fy * h
        alert = self.alerting()
        if alert:  # qualsiasi tocco spegne sveglia/timer
            alert[0].on_action(now)
            return
        for i, b in enumerate(self.renderer.nav_rows(self)):
            if b.x <= px < b.right and b.y <= py < b.bottom:
                self._goto(i)
                return
        hit = self.hit_at(px, py)
        if hit is not None:
            self.page.widget.on_hit(hit, now)
        elif self.page.widget.has_action and self.page.widget.tap_action:
            self.page.widget.on_action(now)

    def hit_at(self, px: float, py: float) -> str | None:
        """Bottone sotto il dito; se nessuno, il più vicino entro `TAP_TOLERANCE`."""
        best, best_d = None, float("inf")
        tol = TAP_TOLERANCE * min(self.frame_size()[0] / 480, self.frame_size()[1] / 320)
        for b, hit in self.renderer.hit_boxes(self):
            dx = max(b.x - px, 0.0, px - b.right)
            dy = max(b.y - py, 0.0, py - b.bottom)
            d = (dx * dx + dy * dy) ** 0.5
            if d == 0:
                return hit
            if d <= tol and d < best_d:
                best, best_d = hit, d
        return best

    def stop(self) -> None:
        self._stop.set()

    # --- disegno ---------------------------------------------------------
    def _rotated(self, img: Image.Image) -> Image.Image:
        rotate = self.cfg["display"]["rotate"]
        return img.rotate(-rotate, expand=True) if rotate else img

    def render(self, now: datetime) -> Image.Image:
        """Fotogramma fermo della pagina corrente (immagine RGB), già ruotato per il pannello."""
        return self._rotated(self.renderer.render(self, now))

    # --- ciclo -----------------------------------------------------------
    def step(self, now: datetime, t: float, animate: bool = True) -> Image.Image | None:
        """Un giro del ciclo: eventi, dati, disegno. Restituisce il fotogramma mostrato, se c'è.

        La pagina base si ridisegna solo quando cambiano i dati (`state_key`); con le animazioni
        attive si mostrano in più `motion.fps` fotogrammi al secondo composti sopra di essa.
        """
        while True:
            try:
                ev = self.events.get_nowait()
            except queue.Empty:
                break
            if isinstance(ev, Tap):
                self.handle_tap(ev, now)
            else:
                self.handle(ev, now)
        for widget in self.widgets.values():
            widget.update(now)
        alert = self.alerting()
        self.buzzer.set(alert is not None)
        if animate and self.page_idx != self._shown_page:
            self.motion.page_changed(self._frame, t)  # scansione dalla pagina di prima
        self._shown_page = self.page_idx
        key = (self.page_idx, tuple(self.widgets), now.strftime("%Y%m%d%H%M"),
               alert[1] if alert else None,
               tuple(w.state_key(now) for w in self.widgets.values()))
        dirty = key != self._last_key
        if dirty:                          # dati cambiati: nuova pagina base
            self._base = self.renderer.render(self, now)
            if animate:
                self.motion.slots_drawn(self.renderer.slots, t)
            self._last_key = key
        fkey = self.motion.frame_key(t) if animate else None
        if self._base is None or not (dirty or fkey != self._last_fkey):
            return None
        self._last_fkey = fkey
        self._frame = (self.renderer.compose(self._base, self, self.motion, t) if animate
                       else self._base)
        shown = self._rotated(self._frame)
        self.display.show(shown)
        return shown

    def run(self, once: bool = False, clock: Any = time.monotonic) -> None:
        """Ciclo principale; `once` disegna un solo fotogramma fermo (niente animazioni)."""
        idle = self.cfg["display"]["tick_s"]
        if not once:
            self.motion.start(clock())
        while not self._stop.is_set():
            t = clock()
            self.step(datetime.now(), t, animate=not once)
            if once:
                break
            # il tempo di disegno conta: si aspetta solo ciò che manca al prossimo fotogramma
            self._stop.wait(max(0.0, self.motion.interval(t, idle) - (clock() - t)))

    def close(self) -> None:
        for widget in self.widgets.values():
            widget.close()
        self.buzzer.set(False)
        self.display.close()
