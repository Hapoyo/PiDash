"""Alba e tramonto calcolati in locale (nessuna rete necessaria).

Algoritmo NOAA semplificato ("Almanac for Computers", 1990); zenit 90,833°
(rifrazione atmosferica + semidiametro solare). Precisione tipica ±1–2 min
alle medie latitudini.
"""
from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone

ZENITH_OFFICIAL = 90.833


def _event_utc(d: date, lat: float, lon: float, rising: bool,
               zenith: float = ZENITH_OFFICIAL) -> datetime | None:
    """Istante UTC dell'alba (rising) o del tramonto; None se il sole non sorge/tramonta."""
    rad, deg = math.radians, math.degrees
    n = d.timetuple().tm_yday
    lng_hour = lon / 15
    t = n + ((6 if rising else 18) - lng_hour) / 24
    m = 0.9856 * t - 3.289                                     # anomalia media
    l_ = (m + 1.916 * math.sin(rad(m)) + 0.020 * math.sin(rad(2 * m)) + 282.634) % 360
    ra = deg(math.atan(0.91764 * math.tan(rad(l_)))) % 360     # ascensione retta
    ra += (math.floor(l_ / 90) * 90) - (math.floor(ra / 90) * 90)
    ra /= 15
    sin_dec = 0.39782 * math.sin(rad(l_))                      # declinazione
    cos_dec = math.cos(math.asin(sin_dec))
    cos_h = (math.cos(rad(zenith)) - sin_dec * math.sin(rad(lat))) / (cos_dec * math.cos(rad(lat)))
    if not -1 <= cos_h <= 1:
        return None
    h = (360 - deg(math.acos(cos_h))) if rising else deg(math.acos(cos_h))
    t_local = h / 15 + ra - 0.06571 * t - 6.622
    ut = (t_local - lng_hour) % 24
    return datetime.combine(d, time(0), timezone.utc) + timedelta(hours=ut)


def sun_times(d: date, lat: float, lon: float) -> tuple[datetime | None, datetime | None]:
    """(alba, tramonto) nel fuso orario locale del sistema."""
    rise = _event_utc(d, lat, lon, rising=True)
    sets = _event_utc(d, lat, lon, rising=False)
    return (rise.astimezone() if rise else None, sets.astimezone() if sets else None)


def hhmm(dt: datetime | None) -> str:
    return dt.strftime("%H:%M") if dt else "--:--"
