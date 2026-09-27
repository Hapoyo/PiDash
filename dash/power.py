"""Alimentazione: il rilevatore di sottotensione del Raspberry, campionato nel tempo.

Il Pi 3 non ha un convertitore analogico: la tensione in volt non si legge. Il firmware però
segnala quando l'ingresso a 5 V scende sotto circa 4,63 V (il "fulmine giallo"). Si legge da:
- hwmon `rpi_volt` (`/sys/class/hwmon/hwmon*/in0_lcrit_alarm`), senza privilegi né processi;
- in mancanza, `vcgencmd get_throttled` (bit 0 = sottotensione adesso).
Lo storico ha una colonna per minuto: 1 se in quel minuto c'è stato almeno un calo, 0 se no.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

THRESHOLD_V = 4.63     # soglia del rilevatore del Raspberry (non regolabile)
SYS_HWMON = Path("/sys/class/hwmon")
BUCKET_S = 60.0        # una colonna del grafico per minuto
SLOTS = 48             # colonne del grafico: gli ultimi 48 minuti


def _find_hwmon(root: Path) -> Path | None:
    """File `in0_lcrit_alarm` del sensore `rpi_volt`, se c'è."""
    try:
        dirs = sorted(root.iterdir())
    except OSError:
        return None
    for d in dirs:
        try:
            if (d / "name").read_text().strip() == "rpi_volt" and (d / "in0_lcrit_alarm").exists():
                return d / "in0_lcrit_alarm"
        except OSError:
            continue
    return None


class PowerMonitor:
    """Stato dell'alimentazione: sotto soglia adesso, storico per minuto, cali contati."""

    def __init__(self, cfg: dict[str, Any] | None = None, hwmon_root: Path = SYS_HWMON,
                 run: Callable[..., Any] = subprocess.run) -> None:
        cfg = cfg or {}
        self.sample_s = max(1.0, float(cfg.get("sample_s", 5)))
        self._run = run
        self._alarm = _find_hwmon(hwmon_root) if cfg.get("monitor", True) else None
        self._vcgencmd = (shutil.which("vcgencmd") if cfg.get("monitor", True)
                          and self._alarm is None else None)
        self.history: deque[int | None] = deque([None] * SLOTS, maxlen=SLOTS)
        self.under = False            # sotto soglia all'ultimo campione
        self.events = 0               # cali da quando il programma è partito
        self.last_event: datetime | None = None
        self._last_sample = -float("inf")
        self._bucket_start: float | None = None
        self.demo = False

    @property
    def source(self) -> str | None:
        """Da dove si legge: "hwmon", "vcgencmd", "demo", oppure None (non disponibile, es. su PC)."""
        if self.demo:
            return "demo"
        return "hwmon" if self._alarm else ("vcgencmd" if self._vcgencmd else None)

    def read(self) -> bool | None:
        """True se l'alimentazione è sotto soglia adesso, None se non si può sapere."""
        if self._alarm is not None:
            try:
                return self._alarm.read_text().strip() == "1"
            except OSError as exc:
                log.warning("sottotensione non leggibile da %s: %s", self._alarm, exc)
                self._alarm = None
                return None
        if self._vcgencmd is not None:
            try:
                r = self._run([self._vcgencmd, "get_throttled"], capture_output=True, text=True,
                              timeout=3)
                return bool(int(r.stdout.strip().split("=")[1], 16) & 0x1)
            except (OSError, subprocess.SubprocessError, ValueError, IndexError) as exc:
                log.warning("vcgencmd get_throttled non riuscito: %s", exc)
                self._vcgencmd = None
        return None

    def sample(self, now: datetime, t: float) -> None:
        """Campiona ogni `sample_s` secondi (tempo monotono `t`), aggiornando lo storico."""
        if t - self._last_sample < self.sample_s:
            return
        self._last_sample = t
        under = self.read()
        if under is None:
            return
        self.record(under, now, t)

    def record(self, under: bool, now: datetime, t: float) -> None:
        """Un campione: nuova colonna ogni `BUCKET_S`, un calo conta quando comincia."""
        if self._bucket_start is None or t - self._bucket_start >= BUCKET_S:
            self._bucket_start = t
            self.history.append(0)
        if under:
            self.history[-1] = 1
            if not self.under:
                self.events += 1
                self.last_event = now
                log.warning("alimentazione sotto %.2f V: alimentatore o cavo insufficiente",
                            THRESHOLD_V)
        self.under = under

    def load_demo(self, now: datetime) -> None:
        """Storico dimostrativo per le anteprime: due cali brevi negli ultimi 48 minuti."""
        self.history = deque([0] * SLOTS, maxlen=SLOTS)
        for i in (13, 14, 37):
            self.history[i] = 1
        self.events, self.last_event, self.under = 2, now.replace(minute=31), False
        self._alarm = self._vcgencmd = None
        self.demo = True

    def state_key(self) -> tuple[Any, ...]:
        return (self.under, self.events, tuple(self.history))
