"""Loop principale: pagine, eventi, aggiornamento dello schermo."""
from __future__ import annotations

import argparse
import logging
import queue
import signal
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image

from . import __version__
from .config import ConfigError, load_config, save_local
from .display import Display, make_display
from .inputs import Buzzer, Event, Tap, start_gpio, start_keyboard, start_touch
from .widgets import ETICHETTE, WIDGET_NAMES, Widget, WidgetFactory
from .widgets.new import NewWidget
from .widgets.system import SystemWidget

log = logging.getLogger("dash")

@dataclass
class Page:
    """Una cartella dello schedario: nome sulla linguetta e widget che ne fornisce i dati."""
    name: str
    widget: Widget
    key: str = ""      # identificatore univoco (es. "timer#2"): più pagine dello stesso tipo
    kind: str = ""     # tipo di widget della pagina


class _MemDisplay(Display):
    """Display senza uscita: serve solo a costruire l'App per le anteprime."""

    def show(self, img: Image.Image) -> None:
        pass


SHOT_TIME = datetime(2026, 9, 24, 7, 42)  # istante fisso: anteprime riproducibili
# Schedario delle anteprime: mostra ogni tipo di pagina, comprese quelle da aggiungere col "+".
SHOT_PAGES = [{"name": "Home", "widget": "clock"}, {"name": "Meteo", "widget": "weather"},
              {"name": "Timer", "widget": "timer"}, {"name": "Sveglia", "widget": "alarm"},
              {"name": "Sistema", "widget": "system"}, {"name": "+", "widget": "new"}]


def _slug(page: Page) -> str:
    """Nome del file dell'anteprima: dal nome della linguetta, o dal tipo se non è scrivibile."""
    s = "".join(c if c.isalnum() else "-" for c in page.name.lower()).strip("-")
    return s or page.kind


def save_screenshots(cfg: dict[str, Any], out_dir: Path, now: datetime = SHOT_TIME) -> list[Path]:
    """Salva un PNG per pagina (`NN-nome.png`) con dati demo e posizione fissa, senza rete.

    Alba e tramonto seguono il fuso del sistema: lanciare con TZ=Europe/Rome fuori dal Pi.
    """
    cfg["weather"]["demo"] = True
    cfg["location"]["mode"] = "fixed"
    cfg["pages"] = [dict(p) for p in SHOT_PAGES]
    d = cfg["display"]
    if "auto" in (d["width"], d["height"]):
        d["width"], d["height"] = 480, 320
    out_dir.mkdir(parents=True, exist_ok=True)
    app = App(cfg, _MemDisplay(d["width"], d["height"]), queue.Queue())
    paths: list[Path] = []
    try:
        for widget in app.widgets.values():
            if isinstance(widget, SystemWidget):
                widget.load_demo()
        for widget in app.widgets.values():
            widget.update(now)
        for i, page in enumerate(app.pages):
            app.page_idx = i
            path = out_dir / f"{i + 1:02d}-{_slug(page)}.png"
            app.renderer.render(app, now).save(path, optimize=True)
            paths.append(path)
    finally:
        app.close()
    return paths


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
        self._renderer: Any = None

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
            page.widget.pagine = self.removable
            page.widget.aggiungi = self.add_page
            page.widget.togli = self.remove_page
        self.pages.insert(len(self.pages) if at is None else at, page)
        self.widgets[key] = page.widget
        return page

    def removable(self) -> list[tuple[str, str]]:
        """Pagine che la scheda "+" può togliere: tutte tranne sé stessa."""
        return [(p.key, p.name) for p in self.pages if p.kind != "new"]

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
            from .cyber import CyberRenderer
            self._renderer = CyberRenderer(self.cfg["theme"].get("palette"))
        return self._renderer

    def _goto(self, idx: int) -> None:
        self.page_idx = idx % len(self.pages)

    def handle_tap(self, tap: Tap, now: datetime) -> None:
        """Linguetta → apre quella cartella; contenuto → azione del widget (timer, sveglia)."""
        rot = self.cfg["display"]["rotate"]
        u, v = tap.x, tap.y  # coordinate del pannello → coordinate del fotogramma
        fx, fy = {0: (u, v), 90: (v, 1 - u), 180: (1 - u, 1 - v), 270: (1 - v, u)}[rot]
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
        for i, b in enumerate(self.renderer.select_boxes(self)):  # voci della scheda "+"
            if b.x <= px < b.right and b.y <= py < b.bottom:
                self.page.widget.on_select(i)
                return
        if self.page.widget.has_action:
            self.page.widget.on_action(now)

    def stop(self) -> None:
        self._stop.set()

    # --- disegno ---------------------------------------------------------
    def render(self, now: datetime) -> Image.Image:
        """Fotogramma della pagina corrente (immagine RGB), già ruotato per il pannello."""
        img = self.renderer.render(self, now)
        rotate = self.cfg["display"]["rotate"]
        return img.rotate(-rotate, expand=True) if rotate else img

    # --- ciclo -----------------------------------------------------------
    def run(self, once: bool = False) -> None:
        d = self.cfg["display"]
        while not self._stop.is_set():
            now = datetime.now()
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
            key = (self.page_idx, tuple(self.widgets), now.strftime("%Y%m%d%H%M"),
                   alert[1] if alert else None,
                   tuple(w.state_key(now) for w in self.widgets.values()))
            if key != self._last_key:      # ridisegna solo quando qualcosa è cambiato
                self.display.show(self.render(now))
                self._last_key = key
            if once:
                break
            self._stop.wait(d["tick_s"])

    def close(self) -> None:
        for widget in self.widgets.values():
            widget.close()
        self.buzzer.set(False)
        self.display.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="pi-dash", description="Dashboard per Raspberry Pi")
    p.add_argument("-c", "--config", default="config.json", type=Path)
    p.add_argument("--driver", choices=("sim", "waveshare", "fb"), help="sovrascrive display.driver")
    p.add_argument("--touch-debug", action="store_true", help="scrive nel log le coordinate di ogni tocco")
    p.add_argument("--log", type=Path, help="scrive il log su file (utile con pythonw)")
    p.add_argument("--once", action="store_true", help="un solo fotogramma ed esci")
    p.add_argument("--page", type=int, default=1, help="pagina iniziale (1…n)")
    p.add_argument("--demo", action="store_true", help="meteo con dati finti (offline)")
    p.add_argument("--screenshots", type=Path, metavar="DIR",
                   help="salva l'anteprima di ogni pagina in DIR ed esci (es. docs/img)")
    p.add_argument("--web", type=int, help="porta del simulatore web (0 = off)")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    handlers: list[logging.Handler] = []
    if args.log:
        args.log.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(args.log, encoding="utf-8"))
    if sys.stderr is not None:  # con pythonw non c'è console
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S", handlers=handlers or [logging.NullHandler()])
    try:
        cfg = load_config(args.config, WIDGET_NAMES)
    except ConfigError as exc:
        log.error("configurazione: %s", exc)
        return 2
    if args.screenshots:
        try:
            for path in save_screenshots(cfg, args.screenshots):
                log.info("anteprima: %s", path)
        except OSError as exc:
            log.error("anteprime: %s", exc)
            return 3
        return 0
    if args.driver:
        cfg["display"]["driver"] = args.driver
    if args.demo:
        cfg["weather"]["demo"] = True
    if args.web is not None:
        cfg["sim"]["web_port"] = args.web
    if args.touch_debug:
        cfg["input"].setdefault("touch", {})["debug"] = True
    if args.once:
        cfg["sim"]["web_port"] = 0
        if cfg["display"]["driver"] == "fb":
            cfg["display"]["driver"] = "sim"
    d = cfg["display"]
    if d["driver"] != "fb" and "auto" in (d["width"], d["height"]):
        d["width"], d["height"] = 480, 320  # 'auto' lo risolve solo il framebuffer

    events: queue.Queue[Any] = queue.Queue()
    try:
        display = make_display(cfg, on_key=lambda k: events.put(Event(k)))
    except (RuntimeError, ValueError, OSError) as exc:
        log.error("display: %s", exc)
        return 3
    app = App(cfg, display, events, config_path=args.config)
    app.page_idx = max(0, min(len(app.pages) - 1, args.page - 1))

    if not args.once:
        if cfg["input"].get("keyboard", True):
            start_keyboard(events)
        touch_cfg = cfg["input"].get("touch") or {}
        if touch_cfg.get("enabled"):
            app.touch = start_touch(events, touch_cfg)
        gpio = cfg["input"].get("gpio")
        if gpio and cfg["display"]["driver"] in ("waveshare", "fb"):
            app.buttons = start_gpio(events, gpio)
        def on_term(*_: Any) -> None:
            app.stop()

        signal.signal(signal.SIGTERM, on_term)

    try:
        app.run(once=args.once)
    except KeyboardInterrupt:
        pass
    finally:
        app.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
