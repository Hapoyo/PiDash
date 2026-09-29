"""Caricamento e validazione della configurazione JSON."""
from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "display": {"driver": "sim", "width": 480, "height": 320, "rotate": 0, "tick_s": 0.5},
    "sim": {"out_dir": "out", "scale": 2, "keep_frames": False,
            "web_host": "127.0.0.1", "web_port": 0},
    "theme": {"palette": {}},
    "location": {"mode": "fixed", "name": "", "city": "", "lat": 0.0, "lon": 0.0, "refresh_h": 6,
                 "gps_device": "", "wifi": True},
    "clock": {"progress": "day"},
    "system": {"sample_s": 2, "refresh_s": 2, "history": 90},
    "weather": {"refresh_min": 30, "cache_dir": "out", "demo": False},
    "timer": {"presets_s": [60, 300, 600], "step_s": 10, "labels": {}},
    "alarm": {"ring_max_min": 10, "alarms": []},
    "pages": [{"name": "Home", "widget": "clock"}],
    "hue": {"bridge": "", "key": "", "timeout_s": 2},
    "needle": {"url": "http://127.0.0.1:8090", "timeout_s": 15, "reset": True,
               "esegui": True, "soglia": 0.6, "soglia_pagine": 0.35, "soglia_luci": 0.4,
               "naviga": True,
               "queries": ["meteo a ventotene", "timer 5 minuti", "apri la pagina sistema",
                           "vai alla home"]},
    "new": {"tipi": ["timer", "alarm", "needle"]},
    "motion": {"livello": "pieno", "fps": 8, "avvio": True},
    "backlight": {"level": 100, "mode": "auto"},
    "power": {"cmd": ["sudo", "-n", "/usr/bin/systemctl", "poweroff"], "monitor": True,
              "sample_s": 5},
    "fb": {"device": "auto", "pixel_scale": 1, "console_off": True},
    "input": {"keyboard": True, "gpio": None, "buzzer_pin": None, "sound": False,
              "touch": {"enabled": False, "device": "auto", "swap_xy": False, "invert_x": False,
                        "invert_y": False, "x_min": None, "x_max": None, "y_min": None,
                        "y_max": None, "debounce_s": 0.15, "debug": False}},
}


class ConfigError(ValueError):
    """Configurazione non valida."""


def _merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    """Unione ricorsiva: i valori di `over` sovrascrivono `base`."""
    out = copy.deepcopy(base)
    for key, val in over.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], val)
        else:
            out[key] = val
    return out


def validate(cfg: dict[str, Any], known_widgets: set[str]) -> None:
    """Solleva ConfigError se la configurazione è incoerente."""
    d = cfg["display"]
    if d["driver"] not in ("sim", "fb"):
        raise ConfigError("display.driver deve essere 'sim' o 'fb'")
    auto = d["width"] == "auto" or d["height"] == "auto"
    if auto and d["driver"] != "fb":
        raise ConfigError("display.width/height 'auto' vale solo con driver 'fb'")
    if not auto and (not isinstance(d["width"], int) or not isinstance(d["height"], int)
                     or d["width"] <= 0 or d["height"] <= 0):
        raise ConfigError("display.width/height devono essere interi > 0 oppure 'auto'")
    if d["rotate"] not in (0, 90, 180, 270):
        raise ConfigError("display.rotate deve essere 0, 90, 180 o 270")
    if cfg["location"]["mode"] not in ("auto", "ip", "city", "fixed"):
        raise ConfigError("location.mode deve essere 'auto', 'ip', 'city' o 'fixed'")
    if cfg["location"]["mode"] == "city" and not (cfg["location"].get("city") or cfg["location"].get("name")):
        raise ConfigError("location.mode 'city' richiede location.city")
    bl = cfg["backlight"]
    if bl.get("mode") not in ("auto", "hw", "sw"):
        raise ConfigError("backlight.mode deve essere 'auto', 'hw' o 'sw'")
    if not isinstance(bl.get("level"), (int, float)) or not 10 <= bl["level"] <= 100:
        raise ConfigError("backlight.level deve essere un numero fra 10 e 100")
    cmd = cfg["power"].get("cmd")
    if cmd is not None and (not isinstance(cmd, list) or not all(isinstance(c, str) for c in cmd)):
        raise ConfigError("power.cmd deve essere una lista di stringhe (o null per disattivarlo)")
    mo = cfg["motion"]
    if mo.get("livello") not in ("off", "eventi", "pieno"):
        raise ConfigError("motion.livello deve essere 'off', 'eventi' o 'pieno'")
    if not isinstance(mo.get("fps"), (int, float)) or not 1 <= mo["fps"] <= 30:
        raise ConfigError("motion.fps deve essere un numero fra 1 e 30")
    hue = cfg["hue"]
    if not isinstance(hue.get("bridge"), str) or not isinstance(hue.get("key"), str):
        raise ConfigError("hue.bridge e hue.key devono essere stringhe (vuote se Hue non si usa)")
    if not isinstance(hue.get("timeout_s"), (int, float)) or not 0.5 <= hue["timeout_s"] <= 30:
        raise ConfigError("hue.timeout_s deve essere un numero fra 0,5 e 30")
    nd = cfg["needle"]
    if not str(nd.get("url", "")).startswith("http://"):
        raise ConfigError("needle.url deve essere un indirizzo http:// (il servizio è locale)")
    for chiave in ("soglia", "soglia_pagine", "soglia_luci"):
        if not isinstance(nd.get(chiave), (int, float)) or not 0 <= nd[chiave] <= 1:
            raise ConfigError(f"needle.{chiave} deve essere un numero fra 0 e 1")
    qs = nd.get("queries")
    if not isinstance(qs, list) or not 1 <= len(qs) <= 6 or not all(isinstance(q, str) for q in qs):
        raise ConfigError("needle.queries deve essere una lista da 1 a 6 frasi")
    if cfg["clock"]["progress"] not in ("day", "daylight", "hour"):
        raise ConfigError("clock.progress deve essere 'day', 'daylight' o 'hour'")
    if not cfg["pages"]:
        raise ConfigError("serve almeno una pagina in 'pages'")
    for i, page in enumerate(cfg["pages"], 1):
        widget = page.get("widget")
        if widget not in known_widgets:
            raise ConfigError(f"pagina {i}: widget '{widget}' sconosciuto "
                              f"(validi: {', '.join(sorted(known_widgets))})")
        if not str(page.get("name", "")).strip():
            raise ConfigError(f"pagina {i}: manca il nome da scrivere sulla linguetta")
    for a in cfg["alarm"]["alarms"]:
        try:
            hh, mm = (int(p) for p in a["time"].split(":"))
        except (KeyError, ValueError) as exc:
            raise ConfigError(f"sveglia non valida: {a}") from exc
        if not (0 <= hh < 24 and 0 <= mm < 60):
            raise ConfigError(f"orario sveglia fuori range: {a['time']}")
        if any(day not in range(7) for day in a.get("days", [])):
            raise ConfigError(f"giorni sveglia: usare 0=lun … 6=dom ({a})")


def local_path(path: str | Path) -> Path:
    """File delle impostazioni personali accanto al principale: config.json → config.local.json."""
    p = Path(path)
    return p.with_name(f"{p.stem}.local{p.suffix}")


def _read_json(p: Path) -> dict[str, Any]:
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"file di configurazione non trovato: {p}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"JSON non valido in {p}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{p}: la radice del JSON deve essere un oggetto")
    return raw


def save_local(path: str | Path, changes: dict[str, Any]) -> Path:
    """Scrive le voci di `changes` in `config.local.json`, conservando le altre.

    Serve alle Impostazioni: pagine, calibrazione, luminosità restano fuori da Git. I dizionari
    si uniscono in profondità: salvare `input.touch` non cancella `input.gpio`.
    """
    local = local_path(path)
    data = _merge(_read_json(local) if local.exists() else {}, changes)
    tmp = local.with_suffix(f"{local.suffix}.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # può contenere la chiave del bridge Hue: un file nuovo nasce 600, uno esistente conserva i permessi
    tmp.chmod(local.stat().st_mode & 0o777 if local.exists() else 0o600)
    tmp.replace(local)  # sostituzione atomica: niente file mezzo scritto se manca corrente
    return local


def load_config(path: str | Path, known_widgets: set[str]) -> dict[str, Any]:
    """Legge il file JSON, applica default e impostazioni personali (`*.local.json`), valida.

    Il file locale non è in Git: `git pull` aggiorna config.json senza toccare le modifiche
    fatte sul Raspberry. Contiene solo le voci da cambiare.
    """
    p = Path(path)
    cfg = _merge(DEFAULTS, _read_json(p))
    local = local_path(p)
    if local.exists():
        cfg = _merge(cfg, _read_json(local))
    validate(cfg, known_widgets)
    if not any(pg["widget"] == "new" for pg in cfg["pages"]):
        # senza la scheda "+" non si possono aggiungere timer e sveglia dal dashboard
        log.warning('nessuna scheda "+" in pages: aggiungi {"name": "+", "widget": "new"} '
                    "in %s per gestire le schede dallo schermo", local if local.exists() else p)
    return cfg
