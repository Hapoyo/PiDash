"""Posizione per meteo e alba/tramonto.

Modalità (`location.mode`):
- "auto":  la migliore disponibile, in ordine: GPS (gpsd o ricevitore NMEA), reti Wi-Fi vicine
           (BeaconDB, precisione di una via), indirizzo IP, coordinate fisse;
- "ip":    posizione stimata dall'indirizzo IP pubblico (livello città: spesso il nodo del
           provider, non il paese vero), con ripiego sulle coordinate fisse;
- "city":  coordinate cercate per nome con l'API di geocoding di Open-Meteo;
- "fixed": solo `lat`/`lon` della configurazione.
Il risultato è salvato in cache (`location.json`) e riletto all'avvio.
"""
from __future__ import annotations

import json
import logging
import math
import os
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

USER_AGENT = "pi-dash (https://github.com/Hapoyo/PiDash)"  # Nominatim chiede un nome riconoscibile
IP_SERVICES = (
    # (url, chiave lat, chiave lon, chiave città) — provati in ordine
    ("https://ipapi.co/json/", "latitude", "longitude", "city"),
    ("http://ip-api.com/json/?fields=status,lat,lon,city", "lat", "lon", "city"),
)
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
BEACONDB_URL = "https://api.beacondb.net/v1/geolocate"   # formato Mozilla Location Service
REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
GPSD = ("127.0.0.1", 2947)
GPS_DEVICES = ("/dev/ttyACM0", "/dev/ttyUSB0")  # ricevitori USB più comuni (u-blox, SiRF)
GPS_WAIT_S = 5.0
NEAR_KM = 10.0   # entro questa distanza dalle coordinate fisse si usa il loro nome
MODES = ("auto", "ip", "city", "fixed")
NET_ERRORS = (urllib.error.URLError, TimeoutError, OSError, ValueError)


def _get_json(url: str, timeout: float = 10, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """GET (o POST JSON se c'è `body`) con risposta JSON a oggetto."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"User-Agent": USER_AGENT}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        out = json.loads(resp.read().decode("utf-8"))
    if not isinstance(out, dict):
        raise ValueError("risposta non valida")
    return out


def _valid(lat: Any, lon: Any) -> bool:
    return (isinstance(lat, (int, float)) and isinstance(lon, (int, float))
            and -90 <= lat <= 90 and -180 <= lon <= 180)


def geocode(city: str, timeout: float = 10) -> tuple[str, float, float] | None:
    """(nome, lat, lon) della città col geocoding di Open-Meteo; None se non esiste.

    Gli errori di rete salgono come `NET_ERRORS`: "non trovata" e "rete assente" sono cose diverse.
    """
    q = urllib.parse.urlencode({"name": city, "count": 1, "language": "it", "format": "json"})
    d = _get_json(f"{GEOCODING_URL}?{q}", timeout=timeout)
    risultati = d.get("results") or []
    if not risultati or not _valid(risultati[0].get("latitude"), risultati[0].get("longitude")):
        return None
    r = risultati[0]
    return str(r.get("name") or city), float(r["latitude"]), float(r["longitude"])


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distanza sulla sfera terrestre (formula dell'emisenoverso)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


# --- GPS ---------------------------------------------------------------------
def parse_nmea(line: str) -> tuple[float, float] | None:
    """(lat, lon) da una frase NMEA RMC o GGA con fix valido e checksum giusto, altrimenti None."""
    line = line.strip()
    if not line.startswith("$") or "*" not in line:
        return None
    body, _, check = line[1:].partition("*")
    calc = 0
    for c in body:
        calc ^= ord(c)
    try:
        if int(check[:2], 16) != calc:
            return None
    except ValueError:
        return None
    f = body.split(",")
    kind = f[0][2:]  # GP, GN, GL… + tipo
    try:
        if kind == "RMC" and len(f) > 6 and f[2] == "A":
            lat_s, ns, lon_s, ew = f[3], f[4], f[5], f[6]
        elif kind == "GGA" and len(f) > 6 and f[6] not in ("", "0"):
            lat_s, ns, lon_s, ew = f[2], f[3], f[4], f[5]
        else:
            return None
        lat = int(lat_s[:2]) + float(lat_s[2:]) / 60
        lon = int(lon_s[:3]) + float(lon_s[3:]) / 60
    except (ValueError, IndexError):
        return None
    lat, lon = (-lat if ns == "S" else lat), (-lon if ew == "W" else lon)
    return (round(lat, 5), round(lon, 5)) if _valid(lat, lon) else None


def _from_gpsd(wait: float = GPS_WAIT_S) -> tuple[float, float] | None:
    """Fix dal demone gpsd (localhost:2947), se installato e con un ricevitore collegato."""
    deadline = time.monotonic() + wait
    try:
        with socket.create_connection(GPSD, timeout=1.0) as s:
            s.sendall(b'?WATCH={"enable":true,"json":true};\n')
            buf = b""
            while time.monotonic() < deadline:
                s.settimeout(max(0.1, deadline - time.monotonic()))
                chunk = s.recv(4096)
                if not chunk:
                    return None
                buf += chunk
                *lines, buf = buf.split(b"\n")
                for ln in lines:
                    try:
                        msg = json.loads(ln)
                    except ValueError:
                        continue
                    if (msg.get("class") == "TPV" and msg.get("mode", 0) >= 2
                            and _valid(msg.get("lat"), msg.get("lon"))):
                        return float(msg["lat"]), float(msg["lon"])
    except OSError:
        return None
    return None


def _from_nmea_device(path: str, wait: float = GPS_WAIT_S) -> tuple[float, float] | None:
    """Fix letto direttamente dalla seriale del ricevitore (senza gpsd)."""
    if os.name != "posix" or not Path(path).exists():
        return None
    import select
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOCTTY", 0))
    except OSError as exc:
        log.debug("gps %s non apribile: %s", path, exc)
        return None
    deadline = time.monotonic() + wait
    buf = b""
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([fd], [], [], max(0.0, deadline - time.monotonic()))
            if not ready:
                break
            chunk = os.read(fd, 1024)
            if not chunk:
                continue
            buf += chunk
            *lines, buf = buf.split(b"\n")
            for ln in lines:
                fix = parse_nmea(ln.decode("ascii", errors="ignore"))
                if fix:
                    return fix
    except OSError as exc:
        log.debug("lettura gps %s: %s", path, exc)
    finally:
        os.close(fd)
    return None


# --- Wi-Fi --------------------------------------------------------------------
def parse_nmcli(text: str) -> list[dict[str, Any]]:
    """Reti da `nmcli -t -f BSSID,SIGNAL dev wifi list` → voci per BeaconDB (dBm stimati)."""
    out = []
    for line in text.splitlines():
        bssid, sep, signal = line.rpartition(":")  # nel BSSID i ":" sono scritti "\:"
        bssid = bssid.replace("\\:", ":").strip().lower()
        if not sep or len(bssid) != 17:
            continue
        try:
            pct = int(signal)
        except ValueError:
            continue
        out.append({"macAddress": bssid, "signalStrength": round(pct / 2 - 100)})
    return out


def _scan_wifi() -> list[dict[str, Any]]:
    if not shutil.which("nmcli"):
        return []
    try:
        r = subprocess.run(["nmcli", "-t", "-f", "BSSID,SIGNAL", "dev", "wifi", "list"],
                           capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug("scansione wi-fi fallita: %s", exc)
        return []
    return parse_nmcli(r.stdout) if r.returncode == 0 else []


class Location:
    """Posizione condivisa (thread-safe) tra meteo e orologio."""

    def __init__(self, cfg: dict[str, Any], cache_dir: str | Path = "out") -> None:
        self.mode = cfg.get("mode", "fixed")
        if self.mode not in MODES:
            raise ValueError(f"location.mode non valido: {self.mode!r}")
        self.city = str(cfg.get("city") or cfg.get("name") or "")
        self.refresh_s = max(1.0, float(cfg.get("refresh_h", 6))) * 3600
        self.gps_device = str(cfg.get("gps_device") or "")
        self.wifi = bool(cfg.get("wifi", True))
        self._lock = threading.Lock()
        self.name = str(cfg.get("name", ""))
        self.lat = float(cfg.get("lat", 0.0))
        self.lon = float(cfg.get("lon", 0.0))
        self._fixed = (self.name, self.lat, self.lon)
        self.source = "fixed"
        self._resolved_at = 0.0
        self.cache_file = Path(cache_dir) / "location.json"
        if self.mode != "fixed":
            self._load_cache()

    # --- stato -----------------------------------------------------------
    def snapshot(self) -> tuple[str, float, float]:
        with self._lock:
            return self.name, self.lat, self.lon

    def kind(self) -> str:
        """Da dove viene la posizione, in breve: "gps", "wifi", "ip", "città" o "fissa"."""
        src = self.source.split(":")[0]
        return {"geocoding": "città", "fixed": "fissa", "cache": "fissa"}.get(src, src)

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
            except NET_ERRORS as exc:
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
        try:
            found = geocode(self.city)
        except NET_ERRORS as exc:
            log.warning("geocoding di %r fallito: %s", self.city, exc)
            return None
        return (*found, "geocoding") if found else None

    def _from_gps(self) -> tuple[str, float, float, str] | None:
        fix = _from_gpsd()
        if fix is None:
            for dev in ((self.gps_device,) if self.gps_device else GPS_DEVICES):
                fix = _from_nmea_device(dev)
                if fix:
                    break
        if fix is None:
            return None
        return self._place(*fix), fix[0], fix[1], "gps"

    def _from_wifi(self) -> tuple[str, float, float, str] | None:
        if not self.wifi:
            return None
        aps = _scan_wifi()
        if len(aps) < 2:  # il servizio chiede almeno due reti per non rivelare un singolo punto
            log.debug("wi-fi: %d reti visibili, poche per la posizione", len(aps))
            return None
        try:
            d = _get_json(BEACONDB_URL, body={"considerIp": False, "wifiAccessPoints": aps})
            loc = d["location"]
            lat, lon = loc["lat"], loc["lng"]
        except (*NET_ERRORS, KeyError, TypeError) as exc:
            log.debug("posizione wi-fi (beacondb) fallita: %s", exc)
            return None
        if not _valid(lat, lon):
            return None
        return self._place(float(lat), float(lon)), float(lat), float(lon), "wifi:beacondb"

    def _place(self, lat: float, lon: float) -> str:
        """Nome del paese per coordinate precise (GPS, Wi-Fi): Nominatim, poi le fisse se vicine."""
        q = urllib.parse.urlencode({"format": "json", "lat": f"{lat:.5f}", "lon": f"{lon:.5f}",
                                    "zoom": 10, "accept-language": "it"})
        try:
            a = _get_json(f"{REVERSE_URL}?{q}").get("address") or {}
            for k in ("city", "town", "village", "municipality", "county"):
                if a.get(k):
                    return str(a[k])
        except NET_ERRORS as exc:
            log.debug("nome del luogo non trovato: %s", exc)
        name, flat, flon = self._fixed
        return name if name and distance_km(lat, lon, flat, flon) <= NEAR_KM else ""

    def _resolve(self) -> tuple[str, float, float, str] | None:
        if self.mode == "city":
            return self._from_city()
        if self.mode == "ip":
            return self._from_ip()
        for step in (self._from_gps, self._from_wifi, self._from_ip):  # "auto"
            found = step()
            if found:
                return found
        return None

    def refresh(self, force: bool = False) -> bool:
        """Aggiorna se scaduta. Ritorna True se le coordinate sono cambiate."""
        if self.mode == "fixed":
            return False
        with self._lock:
            due = force or time.time() - self._resolved_at >= self.refresh_s
        if not due:
            return False
        found = self._resolve()
        if not found:
            log.warning("posizione non determinata: uso %s (%.3f, %.3f)", *self.snapshot())
            return False
        name, lat, lon, source = found
        if source == "gps" or source.startswith("wifi"):
            with self._lock:
                self.name = name  # nome nuovo anche se vuoto: quello vecchio era di un altro posto
        changed = self._set(name, lat, lon, source)
        self._save_cache()
        log.info("posizione: %s %.3f, %.3f (%s)", name, lat, lon, source)
        return changed
