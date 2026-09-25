"""Statistiche del computer: CPU, RAM, disco, temperatura, uptime, rete."""
from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Hashable
from datetime import datetime
from typing import Any

from ..sysinfo import Sampler, Stats
from .base import Widget


def uptime_str(s: float | None) -> str:
    if s is None:
        return "--"
    m = int(s // 60)
    d, m = divmod(m, 1440)
    return f"{d}g {m // 60:02d}h{m % 60:02d}" if d else f"{m // 60:02d}h{m % 60:02d}"


class SystemWidget(Widget):
    name = "system"

    def __init__(self, cfg: dict[str, Any], sampler: Sampler | None = None) -> None:
        super().__init__(cfg)
        self.sample_s = max(0.5, float(cfg.get("sample_s", 2)))
        # Ogni quanto il disegno cambia: basso su monitor, alto su e-ink.
        self.refresh_s = max(self.sample_s, float(cfg.get("refresh_s", 2)))
        self.history: deque[float] = deque(maxlen=int(cfg.get("history", 90)))
        self._sampler = sampler or Sampler()
        self._lock = threading.Lock()
        self._stats = Stats()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            st = self._sampler.sample()
            with self._lock:
                self._stats = st
                if st.cpu is not None:
                    self.history.append(st.cpu)
            self._stop.wait(self.sample_s)

    def update(self, now: datetime) -> None:
        if self._thread is None:
            first = self._sampler.sample()  # RAM/disco subito; la CPU arriva al campione dopo
            with self._lock:
                self._stats = first
            self._thread = threading.Thread(target=self._loop, name="sistema", daemon=True)
            self._thread.start()

    def close(self) -> None:
        self._stop.set()

    def snapshot(self) -> tuple[Stats, list[float]]:
        with self._lock:
            return self._stats, list(self.history)

    def state_key(self, now: datetime) -> Hashable:
        return int(time.monotonic() // self.refresh_s)

    # --- disegno ---------------------------------------------------------
