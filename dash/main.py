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
from .config import ConfigError, load_config
from .display import Display, make_display
from .inputs import Buzzer, Event, Tap, start_gpio, start_keyboard, start_touch
from .widgets import WIDGET_NAMES, Widget, build_widgets

log = logging.getLogger("dash")

@dataclass
class Page:
    """Una cartella dello schedario: nome sulla linguetta e widget che ne fornisce i dati."""
    name: str
    widget: Widget


class App:
    """Stato del dashboard e ciclo di aggiornamento."""

    def __init__(self, cfg: dict[str, Any], display: Display, events: queue.Queue[Any]) -> None:
        self.cfg = cfg
        self.display = display
        self.events = events
        used = {p["widget"] for p in cfg["pages"]}
        self.widgets = build_widgets(used, cfg)
        self.pages = [Page(p["name"], self.widgets[p["widget"]]) for p in cfg["pages"]]
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
            key = (self.page_idx, now.strftime("%Y%m%d%H%M"), alert[1] if alert else None,
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
            if "auto" in (cfg["display"]["width"], cfg["display"]["height"]):
                cfg["display"]["width"], cfg["display"]["height"] = (480, 320)

    events: queue.Queue[Any] = queue.Queue()
    try:
        display = make_display(cfg, on_key=lambda k: events.put(Event(k)))
    except (RuntimeError, ValueError, OSError) as exc:
        log.error("display: %s", exc)
        return 3
    app = App(cfg, display, events)
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
