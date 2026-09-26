"""Riga di comando: legge la configurazione, crea schermo e ingressi, avvia il dashboard."""
from __future__ import annotations

import argparse
import copy
import logging
import queue
import signal
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .app import App
from .config import ConfigError, load_config
from .display import make_display
from .inputs import Event, start_gpio, start_keyboard, start_touch
from .preview import save_animation, save_screenshots
from .widgets import WIDGET_NAMES

log = logging.getLogger("dash")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="pi-dash", description="Dashboard per Raspberry Pi")
    p.add_argument("-c", "--config", default="config.json", type=Path)
    p.add_argument("--driver", choices=("sim", "fb"), help="sovrascrive display.driver")
    p.add_argument("--touch-debug", action="store_true", help="scrive nel log le coordinate di ogni tocco")
    p.add_argument("--log", type=Path, help="scrive il log su file (utile con pythonw)")
    p.add_argument("--once", action="store_true", help="un solo fotogramma ed esci")
    p.add_argument("--page", type=int, default=1, help="pagina iniziale (1…n)")
    p.add_argument("--demo", action="store_true", help="meteo con dati finti (offline)")
    p.add_argument("--screenshots", type=Path, metavar="DIR",
                   help="salva l'anteprima di ogni pagina e la GIF animata in DIR ed esci")
    p.add_argument("--motion", choices=("off", "eventi", "pieno"),
                   help="sovrascrive motion.livello (animazioni)")
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
            for path in save_screenshots(copy.deepcopy(cfg), args.screenshots):
                log.info("anteprima: %s", path)
            anim = save_animation(copy.deepcopy(cfg), args.screenshots / "animazione.gif")
            log.info("anteprima animata: %s (%d kB)", anim, anim.stat().st_size // 1024)
        except OSError as exc:
            log.error("anteprime: %s", exc)
            return 3
        return 0
    if args.driver:
        cfg["display"]["driver"] = args.driver
    if args.motion:
        cfg["motion"]["livello"] = args.motion
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
        if gpio and cfg["display"]["driver"] == "fb":
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
