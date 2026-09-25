"""Statistiche del computer senza dipendenze esterne.

Raspberry Pi (Linux): /proc e /sys, senza dipendenze esterne.
Ogni valore non disponibile vale None: il widget mostra "--".
"""
from __future__ import annotations

import platform
import shutil
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Stats:
    cpu: float | None = None             # 0…1, media dall'ultimo campione
    ram_used: int | None = None          # byte
    ram_total: int | None = None
    disk_used: int | None = None
    disk_total: int | None = None
    temp_c: float | None = None          # temperatura SoC/CPU
    uptime_s: float | None = None
    host: str = field(default_factory=platform.node)
    ip: str | None = None

    @property
    def ram_frac(self) -> float | None:
        return self.ram_used / self.ram_total if self.ram_used is not None and self.ram_total else None

    @property
    def disk_frac(self) -> float | None:
        return self.disk_used / self.disk_total if self.disk_used is not None and self.disk_total else None


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="ascii", errors="ignore")
    except OSError:
        return None


def local_ip() -> str | None:
    """IP locale della scheda usata per uscire (nessun pacchetto viene inviato)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # TEST-NET-1, solo per scegliere l'interfaccia
            return str(s.getsockname()[0])
    except OSError:
        return None


class Sampler:
    """Legge le statistiche; la CPU è calcolata come differenza tra due letture."""

    def __init__(self) -> None:
        self._prev_cpu: tuple[float, float] | None = None  # (occupato, totale)
        self._disk_root = Path.home().anchor or "/"
        self._ip: str | None = None
        self._ip_at = 0.0

    # --- CPU -------------------------------------------------------------
    def _cpu_times(self) -> tuple[float, float] | None:
        line = (_read("/proc/stat") or "").splitlines()[:1]
        if not line or not line[0].startswith("cpu "):
            return None
        v = [float(x) for x in line[0].split()[1:]]
        idle = v[3] + (v[4] if len(v) > 4 else 0.0)  # idle + iowait
        total = sum(v[:8])                              # esclude guest (già in user)
        return total - idle, total

    def _cpu(self) -> float | None:
        cur = self._cpu_times()
        prev, self._prev_cpu = self._prev_cpu, cur
        if cur is None or prev is None or cur[1] <= prev[1]:
            return None
        return max(0.0, min(1.0, (cur[0] - prev[0]) / (cur[1] - prev[1])))

    # --- campione completo ----------------------------------------------
    def sample(self) -> Stats:
        st = Stats(cpu=self._cpu())
        mem = {}
        for line in (_read("/proc/meminfo") or "").splitlines():
            k, _, rest = line.partition(":")
            if rest.strip():
                mem[k] = int(rest.split()[0]) * 1024
        if "MemTotal" in mem and "MemAvailable" in mem:
            st.ram_total, st.ram_used = mem["MemTotal"], mem["MemTotal"] - mem["MemAvailable"]
        up = _read("/proc/uptime")
        st.uptime_s = float(up.split()[0]) if up else None
        t = _read("/sys/class/thermal/thermal_zone0/temp")
        st.temp_c = int(t) / 1000 if t and t.strip().lstrip("-").isdigit() else None
        try:
            du = shutil.disk_usage(self._disk_root)
            st.disk_total, st.disk_used = du.total, du.used
        except OSError:
            pass
        if time.monotonic() - self._ip_at > 300 or self._ip is None:  # l'IP cambia di rado
            self._ip, self._ip_at = local_ip(), time.monotonic()
        st.ip = self._ip
        return st


