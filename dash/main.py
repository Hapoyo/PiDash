"""Riga di comando: legge la configurazione, crea schermo e ingressi, avvia il dashboard."""
from __future__ import annotations

import argparse
import copy
import getpass
import logging
import queue
import signal
import sys
from pathlib import Path
from typing import Any, Callable

from . import __version__
from .app import App
from .config import ConfigError, load_config, save_local
from .hue import LINK_TIMEOUT_S, HueError, registra, scopri
from .display import make_display
from .inputs import Event, Tap, start_gpio, start_keyboard, start_touch
from .preview import save_animation, save_screenshots, save_system_screens
from . import voce, wifi
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
    p.add_argument("--hue-registra", nargs="?", const="", metavar="IP",
                   help="registra PiDash sul bridge Hue (premi il suo tasto) e salva la chiave "
                        "in config.local.json; senza IP lo cerca in rete")
    p.add_argument("--wifi", nargs="?", const="", metavar="SSID",
                   help="cambia le credenziali Wi-Fi del Pi (SSID e password, chieste qui) ed esci")
    p.add_argument("--motion", choices=("off", "eventi", "pieno"),
                   help="sovrascrive motion.livello (animazioni)")
    p.add_argument("--web", type=int, help="porta del simulatore web (0 = off)")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p.parse_args(argv)


def registra_hue(bridge: str, config: Path, send: Any = None) -> int:
    """Chiede al bridge una chiave e la scrive in config.local.json (mai a video né nei log)."""
    try:
        bridge = bridge or scopri()
        print(f"premi il tasto rotondo del bridge Hue {bridge}: hai {int(LINK_TIMEOUT_S)} secondi…",
              flush=True)
        key = registra(bridge, send)
        save_local(config, {"hue": {"bridge": bridge, "key": key}})
    except (HueError, OSError) as exc:
        log.error("hue: %s", exc)
        return 4
    print("PiDash registrato: chiave salvata in config.local.json")
    return 0


def aggiorna_wifi(ssid: str, chiedi: Callable[[str], str] = input,
                  chiedi_segreto: Callable[[str], str] = getpass.getpass,
                  esegui: wifi.Esegui | None = None, root: bool | None = None) -> int:
    """Chiede SSID (se manca) e password (nascosta, due volte) e li salva con `wifi.aggiorna`."""
    esegui = esegui or wifi._esegui
    try:
        try:
            elenco = wifi.reti(esegui)
        except wifi.WifiError as exc:           # senza elenco si può comunque salvare
            log.warning("wifi: %s", exc)
            elenco = []
        if not ssid:
            if elenco:
                print("reti visibili (2,4 GHz = ok per il Pi 3, 5 GHz = no):")
                visti: set[str] = set()
                for nome, mhz, segnale, sicurezza in elenco:
                    if nome not in visti:
                        visti.add(nome)
                        print(f"  {nome}  ({'5' if mhz >= wifi.GHZ5_MHZ else '2,4'} GHz, segnale {segnale}, "
                              f"{sicurezza or 'aperta'})")
            ssid = chiedi("SSID (nome della rete): ")
        for riga in wifi.avvisi(ssid, elenco) if elenco else []:
            print("attenzione:", riga)
        password = chiedi_segreto(f"password di «{ssid}» (non si vede): ")
        if password != chiedi_segreto("ripeti la password: "):
            print("le due password non coincidono: non ho cambiato nulla")
            return 5
        ip = wifi.aggiorna(ssid, password, esegui, root)
    except wifi.WifiError as exc:
        log.error("wifi: %s", exc)
        return 5
    print(f"collegato a «{ssid}»" + (f", indirizzo {ip}" if ip else "") + ": le credenziali restano salvate")
    return 0


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
    if args.wifi is not None:    # prima della configurazione: serve proprio a recuperare un Pi isolato
        return aggiorna_wifi(args.wifi)
    try:
        cfg = load_config(args.config, WIDGET_NAMES)
    except ConfigError as exc:
        log.error("configurazione: %s", exc)
        return 2
    if args.hue_registra is not None:
        return registra_hue(args.hue_registra or cfg["hue"].get("bridge") or "", args.config)
    if args.screenshots:
        try:
            for path in save_screenshots(copy.deepcopy(cfg), args.screenshots):
                log.info("anteprima: %s", path)
            for path in save_system_screens(copy.deepcopy(cfg), args.screenshots):
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
        display = make_display(cfg, on_key=lambda k: events.put(Event(k)),
                               on_tap=lambda x, y: events.put(Tap(x, y)))
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
            app.touch_cal = start_touch(events, touch_cfg)
            app.touch = app.touch_cal is not None
        gpio = cfg["input"].get("gpio")
        if gpio and cfg["display"]["driver"] == "fb":
            app.buttons = start_gpio(events, gpio)
        def on_term(*_: Any) -> None:
            app.stop()

        signal.signal(signal.SIGTERM, on_term)

    # pagina "premi e parla" per il telefono (voce.porta, di norma spenta)
    if not args.once:
        voce.codice(cfg["voce"], lambda changes: save_local(args.config, changes))
    server = None if args.once else voce.avvia(cfg["voce"], events, app.voce_stato,
                                                Path(cfg["sim"]["out_dir"]) / "voce")
    if server is not None:
        app.imposta_voce_url(server.indirizzo())   # QR sulla scheda Needle
    try:
        app.run(once=args.once)
    except KeyboardInterrupt:
        pass
    finally:
        if server is not None:
            server.close()
        app.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
