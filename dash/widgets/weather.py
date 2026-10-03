"""Meteo da Open-Meteo (gratuito, senza chiave API), vento in nodi.

Il download avviene in un thread in background; in caso di errore resta
visibile l'ultimo dato valido (anche dalla cache su disco).
"""
from __future__ import annotations

import json
import logging
import math
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Hashable
from typing import Any

from ..location import Location, geocode
from .base import Widget

log = logging.getLogger(__name__)

API_URL = "https://api.open-meteo.com/v1/forecast"
CURRENT_VARS = ("temperature_2m", "apparent_temperature", "relative_humidity_2m",
                "weather_code", "is_day", "cloud_cover", "pressure_msl",
                "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m")
HOURLY_VARS = ("temperature_2m", "weather_code", "precipitation_probability",
               "soil_temperature_0cm", "soil_temperature_6cm", "wind_speed_10m",
               "wind_gusts_10m", "wind_direction_10m")
DAILY_VARS = ("temperature_2m_max", "temperature_2m_min", "sunrise", "sunset",
              "daylight_duration", "sunshine_duration")

# Fasi lunari: novilunio di riferimento 2000-01-06 18:14 UTC, mese sinodico medio.
_NEW_MOON_REF = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
_SYNODIC_DAYS = 29.530588853
FASI_LUNA = ("NUOVA", "CRESC.", "1°QUARTO", "GIBB.CR.",
             "PIENA", "GIBB.CAL.", "U.QUARTO", "CALANTE")

# Soglie inferiori della scala Beaufort in nodi (forza 1 … 12).
BEAUFORT_KN = (1, 4, 7, 11, 17, 22, 28, 34, 41, 48, 56, 64)
ROSA_16 = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")
VENTI_8 = ("TRAMONTANA", "GRECALE", "LEVANTE", "SCIROCCO",
           "OSTRO", "LIBECCIO", "PONENTE", "MAESTRALE")


def beaufort(kn: float) -> int:
    """Forza Beaufort dalla velocità in nodi."""
    return sum(1 for s in BEAUFORT_KN if round(kn) >= s)


def rosa(deg: float) -> str:
    """Direzione di provenienza su rosa a 16 quarte."""
    return ROSA_16[int((deg % 360) / 22.5 + 0.5) % 16]


def vento_nome(deg: float) -> str:
    """Nome del vento sulla rosa a 8 venti."""
    return VENTI_8[int((deg % 360) / 45 + 0.5) % 8]


# Descrizioni brevi per i riquadri piccoli (display a caratteri).
SHORT = {"POCO NUVOLOSO": "POCO NUV.", "PREV. SERENO": "QUASI SER.", "PIOGGIA GELATA": "GELICIDIO",
         "PIOGG. GELATA": "GELICIDIO", "ROVESCI NEVE": "ROV. NEVE", "TEMP. + GRANDINE": "GRANDINE"}


def moon_phase(when: datetime) -> float:
    """Età della luna in frazione di lunazione (0 = nuova, 0,5 = piena)."""
    aware = when if when.tzinfo else when.astimezone()
    days = (aware - _NEW_MOON_REF).total_seconds() / 86400
    return (days % _SYNODIC_DAYS) / _SYNODIC_DAYS


def moon_illumination(phase: float) -> float:
    """Frazione di disco illuminato (0…1)."""
    return (1 - math.cos(2 * math.pi * phase)) / 2


def moon_name(phase: float) -> str:
    return FASI_LUNA[int(phase * 8 + 0.5) % 8]


def hhmm(seconds: float | None) -> str:
    """Durata in secondi -> 'hh:mm'."""
    if seconds is None:
        return "--:--"
    m = int(seconds // 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def describe(code: int) -> tuple[str, str]:
    """(descrizione italiana, icona) dal codice WMO."""
    table: list[tuple[set[int], str, str]] = [
        ({0}, "SERENO", "sun"), ({1}, "PREV. SERENO", "sun"),
        ({2}, "POCO NUVOLOSO", "partly"), ({3}, "COPERTO", "cloud"),
        ({45, 48}, "NEBBIA", "fog"), ({51, 53, 55}, "PIOGGERELLA", "rain"),
        ({56, 57}, "PIOGG. GELATA", "rain"), ({61, 63, 65}, "PIOGGIA", "rain"),
        ({66, 67}, "PIOGGIA GELATA", "rain"), ({71, 73, 75, 77}, "NEVE", "snow"),
        ({80, 81, 82}, "ROVESCI", "rain"), ({85, 86}, "ROVESCI NEVE", "snow"),
        ({95}, "TEMPORALE", "storm"), ({96, 99}, "TEMP. + GRANDINE", "storm"),
    ]
    for codes, text, icon in table:
        if code in codes:
            return text, icon
    return f"CODICE {code}", "unknown"


class WeatherWidget(Widget):
    name = "weather"

    def __init__(self, cfg: dict[str, Any], location: Location) -> None:
        super().__init__(cfg)
        self.location = location
        self.refresh_s = max(5, int(cfg.get("refresh_min", 30))) * 60
        self.demo = bool(cfg.get("demo", False))
        self.cache_file = Path(cfg.get("cache_dir", "out")) / "weather_cache.json"
        self._lock = threading.Lock()
        self._data: dict[str, Any] | None = self._load_cache()
        if self.demo:
            from ..demo import weather_data  # solo con `weather.demo` o --demo
            self._data = weather_data()
        self._version = 0  # cambia a ogni nuovo scaricamento: usato da state_key
        self.error: str | None = None
        self._stop = threading.Event()
        self._wake = threading.Event()   # scarica subito (città cambiata) invece di aspettare
        self._city: tuple[str, float, float] | None = None   # città temporanea ("meteo roma")
        self._thread: threading.Thread | None = None

    # --- città temporanea --------------------------------------------------
    def place(self) -> tuple[str, float, float]:
        """(nome, lat, lon) di cui si mostra il meteo: la città scelta, altrimenti il luogo del dashboard."""
        with self._lock:
            city = self._city
        return city if city is not None else self.location.snapshot()

    def city(self) -> str:
        """Nome della città temporanea, "" se si segue il luogo del dashboard."""
        with self._lock:
            return self._city[0] if self._city else ""

    def set_city(self, name: str, lat: float, lon: float) -> None:
        """Mostra il meteo di un'altra città fino al riavvio o a `clear_city`; non tocca la posizione."""
        self._switch((name, lat, lon))

    def clear_city(self) -> None:
        """Torna al luogo del dashboard."""
        self._switch(None)

    def _switch(self, city: tuple[str, float, float] | None) -> None:
        with self._lock:
            if city == self._city:
                return
            self._city = city
            if not self.demo:   # i dati di un altro luogo non si mostrano: arrivano quelli nuovi
                self._data = None
            self._version += 1
        self._wake.set()

    # --- dati ------------------------------------------------------------
    @staticmethod
    def _near(data: dict[str, Any], lat: float, lon: float) -> bool:
        """I dati appartengono a questa posizione (griglia del modello ~0,1°)?"""
        try:
            return abs(float(data["latitude"]) - lat) < 0.2 and abs(float(data["longitude"]) - lon) < 0.2
        except (KeyError, TypeError, ValueError):
            return False

    def _load_cache(self) -> dict[str, Any] | None:
        try:
            data = json.loads(self.cache_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        _, lat, lon = self.place()
        return data if isinstance(data, dict) and self._near(data, lat, lon) else None

    def _save_cache(self, data: dict[str, Any]) -> None:
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(self.cache_file)
        except OSError as exc:
            log.warning("cache meteo non salvata: %s", exc)

    def build_url(self) -> str:
        _, lat, lon = self.place()
        params = {
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "current": ",".join(CURRENT_VARS),
            "hourly": ",".join(HOURLY_VARS),
            "daily": ",".join(DAILY_VARS),
            "wind_speed_unit": "kn",
            "timezone": "auto",
            "forecast_days": 2,
        }
        return f"{API_URL}?{urllib.parse.urlencode(params)}"

    def fetch(self) -> bool:
        """Scarica i dati; in caso di errore conserva i precedenti. True se riuscito."""
        try:
            with urllib.request.urlopen(self.build_url(), timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if "current" not in data:
                raise KeyError("risposta senza 'current'")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, OSError) as exc:
            log.warning("meteo non aggiornato: %s", exc)
            with self._lock:
                self.error = "OFFLINE"
            return False
        with self._lock:
            self._data, self._version = data, self._version + 1
            self.error = None
        self._save_cache(data)
        return True

    def _loop(self) -> None:
        retry = 60.0
        while not self._stop.is_set():
            if self.location.refresh():
                # Posizione cambiata: i dati vecchi appartengono a un altro luogo
                # (con una città scelta il meteo non dipende dalla posizione).
                with self._lock:
                    if self._city is None:
                        self._data, self._version = None, self._version + 1
            self._wake.clear()
            if self.fetch():
                retry = 60.0
                self._wake.wait(self.refresh_s)
            else:  # rete non pronta: ritenta con attesa crescente fino al periodo normale
                self._wake.wait(retry)
                retry = min(retry * 2, self.refresh_s)

    def update(self, now: datetime) -> None:
        if self.demo or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="meteo", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self._wake.set()

    def state_key(self, now: datetime) -> Hashable:
        with self._lock:
            return (self._version, self.error, now.strftime("%Y%m%d%H"))

    def snapshot(self) -> dict[str, Any] | None:
        with self._lock:
            return self._data

    # --- dati derivati --------------------------------------------------
    @staticmethod
    def hour_index(data: dict[str, Any]) -> int:
        times: list[str] = data.get("hourly", {}).get("time", [])
        key = str(data["current"].get("time", ""))[:13] + ":00"
        try:
            return times.index(key)
        except ValueError:
            return 0

    @staticmethod
    def hourly(data: dict[str, Any], var: str, idx: int) -> Any:
        vals = data.get("hourly", {}).get(var) or []
        return vals[idx] if 0 <= idx < len(vals) else None

    @staticmethod
    def daily(data: dict[str, Any], var: str) -> Any:
        vals = data.get("daily", {}).get(var) or [None]
        return vals[0]

