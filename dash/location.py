"""Posizione per meteo e alba/tramonto.

Modalità (`location.mode`):
- "ip":    posizione stimata dall'indirizzo IP pubblico (livello città), con ripiego
           sulle coordinate fisse se il servizio non risponde;
- "city":  coordinate cercate per nome con l'API di geocoding di Open-Meteo;
- "fixed": solo `lat`/`lon` della configurazione.
Il risultato è salvato in cache (`location.json`) e riletto all'avvio.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

USER_AGENT = "pi-dash (urllib)"
IP_SERVICES = (
    # (url, chiave lat, chiave lon, chiave città) — provati in ordine
    ("https://ipapi.co/json/", "latitude", "longitude", "city"),
    ("http://ip-api.com/json/?fields=status,lat,lon,city", "lat", "lon", "city"),
)
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
MODES = ("ip", "city", "fixed")


def _get_json(url: str, timeout: float = 10) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("risposta non valida")
    return data


def _valid(lat: Any, lon: Any) -> bool:
    return (isinstance(lat, (int, float)) and isinstance(lon, (int, float))
            and -90 <= lat <= 90 and -180 <= lon <= 180)


class Location:
    """Posizione condivisa (thread-safe) tra meteo e orologio."""

    def __init__(self, cfg: dict[str, Any], cache_dir: str | Path = "out") -> None:
        self.mode = cfg.get("mode", "fixed")
        if self.mode not in MODES:
            raise ValueError(f"location.mode non valido: {self.mode!r}")
        self.city = str(cfg.get("city") or cfg.get("name") or "")
        self.refresh_s = max(1.0, float(cfg.get("refresh_h", 6))) * 3600
        self._lock = threading.Lock()
        self.name = str(cfg.get("name", ""))
        self.lat = float(cfg.get("lat", 0.0))
        self.lon = float(cfg.get("lon", 0.0))
        self.source = "fixed"
        self._resolved_at = 0.0
        self.cache_file = Path(cache_dir) / "location.json"
        if self.mode != "fixed":
            self._load_cache()

    # --- stato -----------------------------------------------------------
    def snapshot(self) -> tuple[str, float, float]:
        with self._lock:
            return self.name, self.lat, self.lon

    def _set(self, name: str, lat: float, lon: float, source: str) -> bool:
        with self._lock:
            changed = abs(lat - self.lat) > 1e-3 or abs(lon - self.lon) > 1e-3
            self.name, self.lat, self.lon, self.source = name or self.name, lat, lon, source
            self._resolved_at = time.time()
        return changed

    def _load_cache(self) -> None:
        try:
            c = json.loads(self.cache_file.read_text(encoding="utf-8"))
            if c.get("mode") == self.mode and _valid(c.get("lat"), c.get("lon")):
                self.name, self.lat, self.lon = c.get("name", self.name), c["lat"], c["lon"]
                self.source = c.get("source", "cache")
                self._resolved_at = float(c.get("time", 0))
        except (OSError, ValueError, KeyError):
            pass

    def _save_cache(self) -> None:
        with self._lock:
            c = {"mode": self.mode, "name": self.name, "lat": self.lat, "lon": self.lon,
                 "source": self.source, "time": self._resolved_at}
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(c), encoding="utf-8")
            tmp.replace(self.cache_file)
        except OSError as exc:
            log.warning("cache posizione non salvata: %s", exc)

    # --- risoluzione -----------------------------------------------------
    def _from_ip(self) -> tuple[str, float, float, str] | None:
        for url, klat, klon, kcity in IP_SERVICES:
            try:
                d = _get_json(url)
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                log.debug("posizione IP da %s fallita: %s", url, exc)
                continue
            if d.get("status", "success") != "success" or not _valid(d.get(klat), d.get(klon)):
                log.debug("posizione IP da %s senza coordinate: %s", url, d)
                continue
            host = urllib.parse.urlparse(url).hostname or url
            return str(d.get(kcity) or ""), float(d[klat]), float(d[klon]), f"ip:{host}"
        return None

    def _from_city(self) -> tuple[str, float, float, str] | None:
        if not self.city:
            return None
        q = urllib.parse.urlencode({"name": self.city, "count": 1, "language": "it", "format": "json"})
        try:
            d = _get_json(f"{GEOCODING_URL}?{q}")
            r = d["results"][0]
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, IndexError) as exc:
            log.warning("geocoding di %r fallito: %s", self.city, exc)
            return None
        if not _valid(r.get("latitude"), r.get("longitude")):
            return None
        return str(r.get("name", self.city)), float(r["latitude"]), float(r["longitude"]), "geocoding"

    def refresh(self, force: bool = False) -> bool:
        """Aggiorna se scaduta. Ritorna True se le coordinate sono cambiate."""
        if self.mode == "fixed":
            return False
        with self._lock:
            due = force or time.time() - self._resolved_at >= self.refresh_s
        if not due:
            return False
        found = self._from_ip() if self.mode == "ip" else self._from_city()
        if not found:
            log.warning("posizione non determinata: uso %s (%.3f, %.3f)", *self.snapshot())
            return False
        name, lat, lon, source = found
        changed = self._set(name, lat, lon, source)
        self._save_cache()
        log.info("posizione: %s %.3f, %.3f (%s)", name, lat, lon, source)
        return changed
