"""Anteprime per il README: un PNG per pagina e la GIF delle animazioni, con dati demo."""
from __future__ import annotations

import queue
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image

from .app import App, Page
from .display import Display
from .motion import BOOT_S
from .widgets.new import NewWidget
from .widgets.system import SystemWidget


class NullDisplay(Display):
    """Display senza uscita: serve solo a costruire l'App per le anteprime."""

    def show(self, img: Image.Image) -> None:
        pass


def _demo(cfg: dict[str, Any], pages: list[dict[str, str]]) -> tuple[int, int]:
    """Meteo finto, posizione fissa, schedario dato: anteprime uguali su ogni macchina."""
    cfg["weather"]["demo"] = True
    cfg["location"]["mode"] = "fixed"
    cfg["pages"] = [dict(p) for p in pages]
    d = cfg["display"]
    if "auto" in (d["width"], d["height"]):
        d["width"], d["height"] = 480, 320
    return d["width"], d["height"]


SHOT_TIME = datetime(2026, 9, 24, 7, 42)  # istante fisso: anteprime riproducibili
# Schedario delle anteprime: mostra ogni tipo di pagina, comprese quelle da aggiungere col "+".
SHOT_PAGES = [{"name": "Home", "widget": "clock"}, {"name": "Meteo", "widget": "weather"},
              {"name": "Timer", "widget": "timer"}, {"name": "Sveglia", "widget": "alarm"},
              {"name": "Sistema", "widget": "system"}, {"name": "+", "widget": "new"}]


def _slug(page: Page) -> str:
    """Nome del file dell'anteprima: dal nome della linguetta, o dal tipo se non è scrivibile."""
    s = "".join(c if c.isalnum() else "-" for c in page.name.lower()).strip("-")
    return s or page.kind


# Copione dell'anteprima animata: (secondi, pagina da aprire all'inizio del tratto).
ANIM_PAGES = [{"name": "Home", "widget": "clock"}, {"name": "Meteo", "widget": "weather"},
              {"name": "Sistema", "widget": "system"}, {"name": "+", "widget": "new"}]
ANIM_SCRIPT = [(BOOT_S + 1.6, None), (1.8, 1), (1.8, 2), (1.2, 3), (1.0, 0)]


def save_animation(cfg: dict[str, Any], path: Path, now: datetime = SHOT_TIME,
                   fps: float = 8.0) -> Path:
    """GIF delle animazioni con dati demo: avvio, poi ogni pagina con il suo cambio."""
    cfg["motion"] = {**cfg.get("motion", {}), "livello": "pieno", "fps": fps, "avvio": True}
    app = App(cfg, NullDisplay(*_demo(cfg, ANIM_PAGES)), queue.Queue())
    frames: list[Image.Image] = []
    try:
        for widget in app.widgets.values():
            if isinstance(widget, SystemWidget):
                widget.load_demo()
        t = 0.0
        app.motion.start(t)
        for secs, page in ANIM_SCRIPT:
            if page is not None:
                app.page_idx = page
            for _ in range(round(secs * fps)):
                shown = app.step(now, t)
                frames.append((shown or frames[-1]).convert("P", palette=Image.Palette.ADAPTIVE,
                                                           colors=64))
                t += 1 / fps
    finally:
        app.close()
    path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=round(1000 / fps),
                   loop=0, optimize=True, disposal=1)
    return path


def save_system_screens(cfg: dict[str, Any], out_dir: Path, now: datetime = SHOT_TIME) -> list[Path]:
    """Schermate fuori dallo schedario e stati: avvio, conferma di spegni, tensione bassa,
    calibrazione, spegnimento."""
    from .inputs import Tap
    from .render import effects
    from .render.theme import unit
    out_dir.mkdir(parents=True, exist_ok=True)
    w, h = _demo(cfg, SHOT_PAGES)
    app = App(cfg, NullDisplay(w, h), queue.Queue())
    paths: list[Path] = []

    def save(name: str, img: Image.Image) -> None:
        path = out_dir / name
        img.save(path, optimize=True)
        paths.append(path)

    try:
        for widget in app.widgets.values():
            widget.update(now)
        save("avvio.png", effects.boot(w, h, unit(w, h), app.renderer.c, app, 0.8))
        app.page_idx = next(i for i, p in enumerate(app.pages) if p.kind == "new")
        app.page.widget.on_hit("spegni", now)          # primo tocco: chiede conferma
        save("spegni-conferma.png", app.renderer.render(app, now))
        app.page.widget._armato = -1e9                 # conferma scaduta
        app.power.load_demo(now)
        app.power.record(True, now, 1e6)               # calo in corso: minuto nuovo, rosa
        save("tensione-bassa.png", app.renderer.render(app, now))
        app.start_calibration()
        assert app.calib is not None
        app.calib.add(Tap(0.1, 0.12))                  # prima croce toccata, tocca alla seconda
        save("calibrazione.png", app.renderer.render(app, now))
        app.calib = None
        app.shutting_down = True
        save("spegnimento.png", app.renderer.render(app, now))
        app.shutting_down = False
    finally:
        app.close()
    return paths


def save_screenshots(cfg: dict[str, Any], out_dir: Path, now: datetime = SHOT_TIME) -> list[Path]:
    """Salva un PNG per pagina (`NN-nome.png`) con dati demo e posizione fissa, senza rete.

    Alba e tramonto seguono il fuso del sistema: lanciare con TZ=Europe/Rome fuori dal Pi.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    app = App(cfg, NullDisplay(*_demo(cfg, SHOT_PAGES)), queue.Queue())
    paths: list[Path] = []
    try:
        for widget in app.widgets.values():
            if isinstance(widget, SystemWidget):
                widget.load_demo()
            if isinstance(widget, NewWidget):
                widget.pagine = dict  # anteprima: catalogo nello stato iniziale (tutto da aggiungere)
        app.power.load_demo(now)
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
