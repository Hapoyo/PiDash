"""Sorgenti di input (tastiera, pulsanti GPIO, touchscreen) e uscita allarme (cicalino)."""
from __future__ import annotations

import logging
import os
import queue
import struct
import sys
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any, NamedTuple

log = logging.getLogger(__name__)


class Event(Enum):
    NEXT = "next"      # pagina successiva
    FOCUS = "focus"    # widget successivo nella pagina
    ACTION = "action"  # pulsante A
    BACK = "back"      # pulsante B
    QUIT = "quit"


class Tap(NamedTuple):
    """Tocco sullo schermo: coordinate 0…1 nell'orientamento del pannello.

    `raw` porta i valori grezzi del controller (serve alla calibrazione a schermo).
    """
    x: float
    y: float
    raw: tuple[int, int] | None = None


def panel_to_frame(x: float, y: float, rotate: int) -> tuple[float, float]:
    """Coordinate 0…1 del pannello → coordinate 0…1 del fotogramma disegnato (prima della rotazione)."""
    return {0: (x, y), 90: (y, 1 - x), 180: (1 - x, 1 - y), 270: (1 - y, x)}[rotate]


def frame_to_panel(x: float, y: float, rotate: int) -> tuple[float, float]:
    """Inversa di `panel_to_frame`: un punto del fotogramma nelle coordinate del pannello."""
    return {0: (x, y), 90: (1 - y, x), 180: (1 - x, 1 - y), 270: (y, 1 - x)}[rotate]


KEYMAP: dict[str, Event] = {"n": Event.NEXT, "f": Event.FOCUS, "a": Event.ACTION,
                            "b": Event.BACK, "q": Event.QUIT}


def start_keyboard(q: queue.Queue[Event]) -> None:
    """Legge comandi da stdin (una lettera + Invio). Solo se è un terminale."""
    if not sys.stdin or not sys.stdin.isatty():
        return

    def loop() -> None:
        for line in sys.stdin:
            ev = KEYMAP.get(line.strip().lower()[:1])
            if ev:
                q.put(ev)
            if ev is Event.QUIT:
                return

    threading.Thread(target=loop, name="tastiera", daemon=True).start()
    log.info("tastiera: n=pagina f=focus a=azione b=indietro q=esci (+Invio)")


def start_gpio(q: queue.Queue[Event], pins: dict[str, int]) -> list[Any]:
    """Collega i pulsanti GPIO (numerazione BCM, verso GND con pull-up)."""
    try:
        from gpiozero import Button  # type: ignore[import-not-found]
    except ImportError:
        log.warning("gpiozero non installato: pulsanti GPIO disattivati")
        return []
    buttons: list[Any] = []
    for name, pin in pins.items():
        try:
            ev = Event(name)
        except ValueError:
            log.warning("input.gpio: tasto sconosciuto %r ignorato", name)
            continue
        try:
            btn = Button(pin, pull_up=True, bounce_time=0.05)
        except Exception as exc:  # gpiozero solleva vari tipi a seconda del backend
            log.error("GPIO%s (%s) non disponibile: %s", pin, name, exc)
            continue
        btn.when_pressed = lambda e=ev: q.put(e)
        buttons.append(btn)
    return buttons


# --- touchscreen (evdev, senza dipendenze) ---------------------------------
EV_SYN, EV_KEY, EV_ABS = 0x00, 0x01, 0x03
ABS_X, ABS_Y, ABS_PRESSURE = 0x00, 0x01, 0x18
BTN_TOUCH = 0x14A
_EVENT = struct.Struct("llHHi")  # struct input_event (timeval nativo)


def _eviocgabs(code: int) -> int:
    """_IOR('E', 0x40 + code, struct input_absinfo) — 6 interi = 24 byte."""
    return (2 << 30) | (24 << 16) | (ord("E") << 8) | (0x40 + code)


def find_touch_device(text: str | None = None) -> str | None:
    """/dev/input/eventN del touchscreen (es. "ADS7846 Touchscreen")."""
    if text is None:
        p = Path("/proc/bus/input/devices")
        text = p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""
    for block in text.split("\n\n"):
        name = next((ln for ln in block.splitlines() if ln.startswith("N: ")), "")
        handlers = next((ln for ln in block.splitlines() if ln.startswith("H: ")), "")
        if "touch" in name.lower() or "ads7846" in name.lower():
            ev = next((h for h in handlers.split() if h.startswith("event")), None)
            if ev:
                return f"/dev/input/{ev}"
    return None


def tap_from_samples(samples: list[tuple[int, int]]) -> tuple[int, int] | None:
    """Punto grezzo di un tocco dai campioni raccolti mentre il dito preme.

    Il resistivo XPT2046 sbaglia di più all'appoggio e al distacco (la pressione cala): si
    scartano il primo e gli ultimi due campioni, poi la mediana per asse toglie i salti.
    """
    if not samples:
        return None
    keep = samples[1:-2] if len(samples) >= 6 else samples
    xs = sorted(s[0] for s in keep)
    ys = sorted(s[1] for s in keep)
    return xs[len(xs) // 2], ys[len(ys) // 2]


class TouchCalibration:
    """Porta i valori grezzi del controller in 0…1, con scambio/inversione degli assi."""

    def __init__(self, cfg: dict[str, Any], ranges: dict[int, tuple[int, int]]) -> None:
        self.ranges = ranges
        self.apply(cfg)

    def apply(self, cfg: dict[str, Any]) -> None:
        """Nuovi estremi e orientamento, anche mentre il touch è in uso (calibrazione a schermo)."""
        def pick(key: str, default: int) -> int:
            val = cfg.get(key)
            return int(val) if val is not None else default
        rx, ry = self.ranges[ABS_X], self.ranges[ABS_Y]
        self.x_min, self.x_max = pick("x_min", rx[0]), pick("x_max", rx[1])
        self.y_min, self.y_max = pick("y_min", ry[0]), pick("y_max", ry[1])
        self.swap = bool(cfg.get("swap_xy", False))
        self.inv_x = bool(cfg.get("invert_x", False))
        self.inv_y = bool(cfg.get("invert_y", False))

    def map(self, raw_x: int, raw_y: int) -> Tap:
        def norm(v: int, lo: int, hi: int) -> float:
            return min(1.0, max(0.0, (v - lo) / (hi - lo))) if hi != lo else 0.0
        x, y = norm(raw_x, self.x_min, self.x_max), norm(raw_y, self.y_min, self.y_max)
        if self.swap:
            x, y = y, x
        return Tap(1 - x if self.inv_x else x, 1 - y if self.inv_y else y, (raw_x, raw_y))


def start_touch(q: queue.Queue[Any], cfg: dict[str, Any]) -> TouchCalibration | None:
    """Avvia la lettura del touchscreen; un tocco rilasciato diventa un evento Tap.

    Restituisce la calibrazione in uso (modificabile a caldo), None se il touch non c'è.
    """
    import fcntl

    device = cfg.get("device") or "auto"
    path = find_touch_device() if device == "auto" else str(device)
    if not path:
        log.warning("touchscreen non trovato (dtoverlay con ads7846?)")
        return None
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError as exc:
        log.warning("touchscreen %s non apribile (gruppo 'input'?): %s", path, exc)
        return None
    ranges = {}
    for code in (ABS_X, ABS_Y):
        try:
            buf = fcntl.ioctl(fd, _eviocgabs(code), bytes(24))
            _, lo, hi, *_ = struct.unpack("6i", buf)
            ranges[code] = (lo, hi)
        except OSError:
            ranges[code] = (0, 4095)
    cal = TouchCalibration(cfg, ranges)
    debug = bool(cfg.get("debug", False))
    min_gap = float(cfg.get("debounce_s", 0.15))

    def loop() -> None:
        raw = [0, 0]
        pressure: int | None = None      # None se il controller non la riporta
        samples: list[tuple[int, int]] = []
        down = False
        last_tap = 0.0
        while True:
            try:
                data = os.read(fd, _EVENT.size)
            except OSError as exc:
                log.error("lettura touchscreen interrotta: %s", exc)
                return
            if len(data) < _EVENT.size:
                continue
            _, _, etype, code, value = _EVENT.unpack(data)
            if etype == EV_ABS and code in (ABS_X, ABS_Y):
                raw[0 if code == ABS_X else 1] = value
            elif etype == EV_ABS and code == ABS_PRESSURE:
                pressure = value
            elif etype == EV_SYN and down and (pressure is None or pressure > 0):
                samples.append((raw[0], raw[1]))   # un campione completo per ogni SYN_REPORT
            elif etype == EV_KEY and code == BTN_TOUCH and value == 1:   # dito appoggiato
                down, samples = True, []
            elif etype == EV_KEY and code == BTN_TOUCH and value == 0:   # dito sollevato
                down = False
                now = time.monotonic()
                if now - last_tap < min_gap:
                    continue
                last_tap = now
                point = tap_from_samples(samples) or (raw[0], raw[1])
                tap = cal.map(*point)
                if debug:
                    log.info("tocco: grezzo x=%d y=%d (%d campioni) → %.2f, %.2f",
                             point[0], point[1], len(samples), tap.x, tap.y)
                q.put(tap)

    threading.Thread(target=loop, name="touch", daemon=True).start()
    log.info("touchscreen %s (x %d…%d, y %d…%d)", path, cal.x_min, cal.x_max, cal.y_min, cal.y_max)
    return cal


class Buzzer:
    """Allarme acustico: cicalino su GPIO oppure campanella del terminale."""

    def __init__(self, pin: int | None, sound: bool = False) -> None:
        self._dev: Any = None
        self._on = threading.Event()
        self._sound = sound and pin is None
        if pin is None:
            return
        try:
            from gpiozero import Buzzer as GzBuzzer  # type: ignore[import-not-found]
            self._dev = GzBuzzer(pin)
        except Exception as exc:
            log.warning("buzzer su GPIO%s non disponibile: %s", pin, exc)

    def _beep_loop(self) -> None:
        """Bip intermittente finché l'allarme è attivo."""
        def beep() -> None:  # campanella del terminale, se non c'è il cicalino su GPIO
            sys.stdout.write("\a")
            sys.stdout.flush()

        while self._on.is_set():
            try:
                beep()
            except (RuntimeError, OSError) as exc:  # nessuna scheda audio / console
                log.warning("suono non disponibile: %s", exc)
                return
            time.sleep(0.8)

    def set(self, on: bool) -> None:
        if on == self._on.is_set():
            return
        if on:
            self._on.set()
        else:
            self._on.clear()
        if self._dev:
            if on:
                self._dev.beep(on_time=0.2, off_time=0.8)
            else:
                self._dev.off()
        elif self._sound and on:
            threading.Thread(target=self._beep_loop, name="bip", daemon=True).start()
        log.info("[buzzer] %s", "ON" if on else "OFF")
