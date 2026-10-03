"""Dati dimostrativi per anteprime, simulatore (`--demo`) e test.

Non fa parte dell'esecuzione normale sul Pi: i widget lo importano solo quando serve
(`weather.demo`, `--demo`, `load_demo()`).
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from .sysinfo import Stats

GIB = 1024 ** 3
# Dati finti per le anteprime: un Pi 3 a riposo (RAM 1 GB, SD 32 GB).
DEMO_STATS = Stats(cpu=0.12, ram_used=int(0.21 * GIB), ram_total=GIB, disk_used=int(4.1 * GIB),
                   disk_total=int(29.1 * GIB), temp_c=48.3, net_rx=42_000, net_tx=7_300,
                   uptime_s=3 * 86400 + 5 * 3600 + 12 * 60, host="pi-dash", ip="192.168.1.20")
DEMO_CPU = (0.08, 0.10, 0.07, 0.12, 0.31, 0.45, 0.22, 0.11, 0.09, 0.14, 0.38, 0.17,
            0.10, 0.08, 0.12, 0.26, 0.19, 0.09, 0.07, 0.11, 0.35, 0.52, 0.28, 0.12)
DEMO_NET = (1_200, 800, 15_000, 62_000, 48_000, 9_000, 2_100, 900, 1_500, 31_000, 74_000, 22_000,
            3_400, 1_100, 800, 12_000, 55_000, 18_000, 2_600, 1_000, 900, 7_800, 49_000, 11_000)


def weather_data() -> dict[str, Any]:
    """Dati finti coerenti per lavorare offline."""
    start = datetime(2026, 9, 23)
    times, temps, codes, rain, soil0, soil6 = [], [], [], [], [], []
    wind: list[float] = []
    gust: list[float] = []
    for h in range(48):
        t = start + timedelta(hours=h)
        times.append(t.strftime("%Y-%m-%dT%H:00"))
        temps.append(round(21 + 4 * math.sin((t.hour - 9) / 24 * 2 * math.pi), 1))
        codes.append((0, 1, 2, 2, 3, 61, 2, 0)[(h // 3) % 8])
        rain.append((5, 10, 16, 30, 55, 40, 20, 8)[(h // 3) % 8])
        soil0.append(round(temps[-1] - 1, 1))
        soil6.append(round(temps[-1] - 6, 1))
        wind.append(round(9 + 6 * math.sin((t.hour - 6) / 24 * 2 * math.pi) + (h % 3), 1))
        gust.append(round(wind[-1] * 1.4, 1))
    return {
        "current": {"time": "2026-09-23T14:30", "temperature_2m": 24.7,
                    "apparent_temperature": 26.1, "relative_humidity_2m": 73,
                    "weather_code": 2, "is_day": 1, "cloud_cover": 22,
                    "pressure_msl": 1013.4, "wind_speed_10m": 14.2,
                    "wind_direction_10m": 315, "wind_gusts_10m": 21.0},
        "hourly": {"time": times, "temperature_2m": temps, "weather_code": codes,
                   "precipitation_probability": rain,
                   "soil_temperature_0cm": soil0, "soil_temperature_6cm": soil6,
                   "wind_speed_10m": wind, "wind_gusts_10m": gust,
                   "wind_direction_10m": [300] * 48},
        "daily": {"temperature_2m_max": [25.1], "temperature_2m_min": [19.2],
                  "sunrise": ["2026-09-23T06:52"], "sunset": ["2026-09-23T18:59"],
                  "daylight_duration": [43620.0], "sunshine_duration": [36900.0]},
    }
