"""Motion graphics: tempi e stato delle animazioni (il disegno è in `dash/cyber.py`).

Tre livelli (`motion.livello`):
- "off":    nessuna animazione, schermo aggiornato solo quando cambia un dato;
- "eventi": animazioni brevi sugli eventi — avvio, cambio pagina, numeri che cambiano;
- "pieno":  in più gli effetti continui (sfere che pulsano, due punti che lampeggiano,
            radar sulla bussola, cursore sui grafici, spia della linguetta).

Tutto dipende da un tempo `t` in secondi (monotono) passato dall'esterno: i test e le anteprime
usano tempi fissi.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from PIL import Image

LIVELLI = ("off", "eventi", "pieno")
BOOT_S = 2.4        # sequenza di avvio
WIPE_S = 0.45       # scansione al cambio pagina
DECODE_S = 0.55     # cifre che "si decodificano" prima di fermarsi
GLIFI = "0123456789"


def ease_out(x: float) -> float:
    """Decelerazione cubica: parte veloce, arriva morbida (0…1 → 0…1)."""
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def ease_in_out(x: float) -> float:
    """Accelera e rallenta (0…1 → 0…1)."""
    x = max(0.0, min(1.0, x))
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def wave(t: float, period: float, phase: float = 0.0) -> float:
    """Onda 0…1…0 di periodo `period` secondi: pulsazioni e lampeggi morbidi."""
    x = ((t / period) + phase) % 1.0
    return 1 - abs(2 * x - 1)


@dataclass(frozen=True)
class Slot:
    """Numero grande registrato durante il disegno: può "decodificarsi" quando cambia."""
    key: str                      # es. "clock.ora", "weather.temp"
    text: str
    xy: tuple[float, float]
    anchor: str
    font: Any                     # ImageFont.FreeTypeFont
    fill: str                     # nome del colore del testo
    bg: str                       # nome del colore del fondo su cui sta il numero
    box: tuple[int, int, int, int]  # rettangolo del testo finale, già con margine
    live: bool = False            # cambia spesso (cpu, timer): si decodifica solo all'apertura


@dataclass(frozen=True)
class Fx:
    """Effetto continuo registrato durante il disegno (livello "pieno")."""
    kind: str                     # "pulse", "blink", "sweep", "scan", "led", "outline"
    box: tuple[int, int, int, int]
    color: str = "cream"
    bg: str = "panel"
    phase: float = 0.0
    extra: tuple[float, ...] = ()


@dataclass
class _Decode:
    slot: Slot
    start: float
    keep: str = ""  # testo precedente: le cifre rimaste uguali non si muovono


@dataclass
class Motion:
    """Stato delle animazioni in corso; il ciclo principale lo interroga a ogni giro."""
    livello: str = "pieno"
    fps: float = 8.0
    avvio: bool = True
    boot_start: float | None = None
    wipe_from: Image.Image | None = None
    wipe_start: float = 0.0
    decodes: list[_Decode] = field(default_factory=list)
    _slots: dict[str, Slot] = field(default_factory=dict)

    @classmethod
    def from_cfg(cls, cfg: dict[str, Any]) -> Motion:
        livello = str(cfg.get("livello", "pieno"))
        if livello not in LIVELLI:
            raise ValueError(f"motion.livello deve essere uno di {LIVELLI}")
        fps = float(cfg.get("fps", 8))
        return cls(livello=livello, fps=max(1.0, min(30.0, fps)), avvio=bool(cfg.get("avvio", True)))

    @property
    def on(self) -> bool:
        return self.livello != "off"

    @property
    def ambient(self) -> bool:
        return self.livello == "pieno"

    # --- eventi --------------------------------------------------------------
    def start(self, t: float) -> None:
        """Avvio del programma: sequenza di accensione, se abilitata."""
        if self.on and self.avvio:
            self.boot_start = t

    def skip_boot(self) -> None:
        self.boot_start = None

    def page_changed(self, old_frame: Image.Image | None, t: float) -> None:
        """Cambio pagina: scansione dall'alto che rivela la nuova cartella."""
        if not self.on or old_frame is None:
            return
        self.wipe_from = old_frame
        self.wipe_start = t
        self._slots = {}  # i numeri della nuova pagina entrano decodificandosi

    def slots_drawn(self, slots: list[Slot], t: float) -> None:
        """Numeri appena disegnati: quelli nuovi o cambiati partono con la decodifica."""
        if not self.on:
            self._slots = {s.key: s for s in slots}
            return
        delay = WIPE_S * 0.6 if self.wipe_from is not None else 0.0
        for s in slots:
            old = self._slots.get(s.key)
            if old is not None and (old.text == s.text or s.live):
                continue
            self.decodes = [d for d in self.decodes if d.slot.key != s.key]
            self.decodes.append(_Decode(s, t + delay, old.text if old else ""))
        self._slots = {s.key: s for s in slots}

    # --- stato nel tempo -----------------------------------------------------
    def boot_progress(self, t: float) -> float | None:
        """0…1 durante l'avvio, None quando è finito."""
        if self.boot_start is None:
            return None
        p = (t - self.boot_start) / BOOT_S
        if p >= 1:
            self.boot_start = None
            return None
        return max(0.0, p)

    def wipe_progress(self, t: float) -> float | None:
        """0…1 durante la scansione di cambio pagina, None quando è finita."""
        if self.wipe_from is None:
            return None
        p = (t - self.wipe_start) / WIPE_S
        if p >= 1:
            self.wipe_from = None
            return None
        return ease_out(p)

    def active_decodes(self, t: float) -> list[tuple[Slot, float, str]]:
        """(numero, avanzamento 0…1, testo precedente) delle decodifiche in corso."""
        self.decodes = [d for d in self.decodes if t - d.start < DECODE_S]
        return [(d.slot, max(0.0, (t - d.start) / DECODE_S), d.keep) for d in self.decodes]

    def busy(self, t: float) -> bool:
        """True se c'è un'animazione a evento in corso (avvio, scansione, decodifica)."""
        return (self.boot_start is not None or self.wipe_from is not None
                or any(t - d.start < DECODE_S for d in self.decodes))

    def interval(self, t: float, idle: float) -> float:
        """Attesa prima del prossimo giro del ciclo: veloce se qualcosa si muove."""
        if self.busy(t) or self.ambient:
            return min(idle, 1.0 / self.fps)
        return idle

    def frame_key(self, t: float) -> int | None:
        """Numero del fotogramma animato (cambia `fps` volte al secondo), None se fermo."""
        if self.busy(t) or self.ambient:
            return int(t * self.fps)
        return None


def scramble(text: str, progress: float, seed: int, keep: str = "") -> str:
    """Testo durante la decodifica: le cifre si fermano da sinistra a destra.

    Solo le cifre cambiano; ":" "°" "%" e le lettere restano al loro posto, e così le cifre
    uguali a quelle di `keep` (testo precedente della stessa lunghezza): 07:42 → 07:43 muove
    solo l'ultima.
    """
    rnd = random.Random(seed)
    same = len(keep) == len(text)
    digits = [i for i, c in enumerate(text) if c.isdigit() and not (same and keep[i] == c)]
    if not digits:
        return text
    out = list(text)
    for n, i in enumerate(digits):
        settle = (n + 1) / (len(digits) + 1)  # ogni cifra si ferma un po' dopo la precedente
        if progress < settle:
            out[i] = rnd.choice(GLIFI)
    return "".join(out)
