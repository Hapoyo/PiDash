"""Test di base: python -m unittest -v"""
from __future__ import annotations

import copy
import json
import queue
import tempfile
import time
import unittest
from typing import Any
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageChops

from dash import azioni
from dash.config import DEFAULTS, ConfigError, _merge, validate
from dash.display.base import Display
from dash.hue import Hue, HueError, registra
from dash.inputs import Event, Tap
from dash.app import App
from dash.widgets import WIDGET_NAMES
from dash.widgets.alarm import AlarmWidget
from dash.widgets.needle import NeedleWidget
from dash.widgets.needle import parse as parse_needle
from dash.widgets.timer import TimerState, TimerWidget
from dash.widgets.weather import (beaufort, describe, moon_illumination, moon_phase,
                                  rosa, vento_nome)


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class MemDisplay(Display):
    def __init__(self, w: int, h: int) -> None:
        super().__init__(w, h)
        self.frames: list[Image.Image] = []

    def show(self, img: Image.Image) -> None:
        self.frames.append(img)


def make_cfg(**over: object) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    cfg["weather"]["demo"] = True
    cfg["pages"] = [
        {"name": "Home", "widget": "clock"},
        {"name": "Meteo", "widget": "weather"},
        {"name": "Timer", "widget": "timer"},
        {"name": "Sveglia", "widget": "alarm"},
        {"name": "Sistema", "widget": "system"},
        {"name": "+", "widget": "new"},
    ]
    return _merge(cfg, over)


class TestConfig(unittest.TestCase):
    def test_default_valid(self) -> None:
        validate(make_cfg(), WIDGET_NAMES)

    def test_unknown_widget(self) -> None:
        cfg = make_cfg()
        cfg["pages"][0]["widget"] = "inesistente"
        with self.assertRaises(ConfigError):
            validate(cfg, WIDGET_NAMES)

    def test_page_needs_a_name(self) -> None:
        cfg = make_cfg()
        cfg["pages"][0]["name"] = " "
        with self.assertRaises(ConfigError):
            validate(cfg, WIDGET_NAMES)

    def test_shipped_config_valid(self) -> None:
        """Il config.json del progetto, letto da solo: il file locale del Pi non deve influire."""
        from dash.config import load_config
        shipped = Path(__file__).parent.parent / "config.json"
        with tempfile.TemporaryDirectory() as tmp:
            copia = Path(tmp) / "config.json"
            copia.write_bytes(shipped.read_bytes())
            cfg = load_config(copia, WIDGET_NAMES)
        self.assertEqual(cfg["display"]["driver"], "fb")
        # timer e sveglia non ci sono: si aggiungono dalla scheda "+"
        self.assertEqual([p["name"] for p in cfg["pages"]], ["Home", "Meteo", "Sistema", "+"])
        self.assertEqual(cfg["new"]["tipi"], ["timer", "alarm", "needle"])  # catalogo del "+"

    def test_local_pages_do_not_break_the_shipped_config(self) -> None:
        """Uno schedario personale (senza "+") resta valido: solo un avviso nel log."""
        from dash.config import load_config
        shipped = Path(__file__).parent.parent / "config.json"
        with tempfile.TemporaryDirectory() as tmp:
            copia = Path(tmp) / "config.json"
            copia.write_bytes(shipped.read_bytes())
            (Path(tmp) / "config.local.json").write_text(
                json.dumps({"pages": [{"name": "Home", "widget": "clock"},
                                      {"name": "Timer", "widget": "timer"}]}), encoding="utf-8")
            with self.assertLogs("dash.config", "WARNING") as log:
                cfg = load_config(copia, WIDGET_NAMES)
        self.assertEqual([p["name"] for p in cfg["pages"]], ["Home", "Timer"])
        self.assertIn("+", log.output[0])

    def test_bad_alarm(self) -> None:
        cfg = make_cfg()
        cfg["alarm"]["alarms"] = [{"time": "25:00"}]
        with self.assertRaises(ConfigError):
            validate(cfg, WIDGET_NAMES)


class TestTimer(unittest.TestCase):
    def test_cycle(self) -> None:
        clk = FakeClock()
        t = TimerWidget({"presets_s": [60], "step_s": 10}, clock=clk)
        now = datetime.now()
        t.on_action(now)
        self.assertIs(t.state, TimerState.RUNNING)
        clk.t += 25
        self.assertEqual(t.shown_remaining(), 40)  # 35 s arrotondati al passo
        t.on_action(now)
        self.assertIs(t.state, TimerState.PAUSED)
        clk.t += 100
        self.assertAlmostEqual(t.remaining(), 35)
        t.on_action(now)
        clk.t += 36
        t.update(now)
        self.assertIs(t.state, TimerState.DONE)
        self.assertIsNotNone(t.alert())
        t.on_action(now)
        self.assertIs(t.state, TimerState.IDLE)

    def test_back_adds_the_first_preset(self) -> None:
        t = TimerWidget({"presets_s": [300, 60]})
        self.assertEqual(t.duration, 300)          # all'accensione il primo della lista
        t.on_back(datetime.now())
        self.assertEqual(t.duration, 360)          # B somma il preset più corto

    def test_buttons_add_subtract_and_clear(self) -> None:
        clk = FakeClock()
        now = datetime(2026, 9, 24, 7, 42)
        t = TimerWidget({"presets_s": [900, 60, 300, 600], "labels": {"300": "pasta"}},
                        clock=clk)
        self.assertEqual([h for h, _ in t.buttons()],
                         ["sub", "add:60", "add:300", "add:600", "add:900", "clear"])
        self.assertEqual(dict(t.buttons())["sub"], "−1'")
        self.assertEqual((t.duration, t.label()), (300, "PASTA"))  # parte dalla durata con nome
        t.on_hit("add:300", now)
        t.on_hit("add:300", now)
        self.assertEqual(t.shown_remaining(), 900)                     # si sommano
        self.assertEqual(t.flashing(), "add:300")
        clk.t += 1
        self.assertEqual(t.flashing(), "")
        t.on_hit("sub", now)
        self.assertEqual(t.shown_remaining(), 840)
        t.on_hit("clear", now)
        t.on_hit("sub", now)
        self.assertEqual((t.shown_remaining(), t.duration), (0, 0))    # mai sotto zero
        t.on_action(now)
        self.assertIs(t.state, TimerState.IDLE)                        # a zero non parte

    def test_adding_while_running_moves_the_deadline(self) -> None:
        clk = FakeClock()
        now = datetime(2026, 9, 24, 7, 42)
        t = TimerWidget({"presets_s": [60], "step_s": 1}, clock=clk)
        t.on_action(now)
        clk.t += 50
        t.on_hit("add:60", now)
        self.assertEqual(t.shown_remaining(), 70)
        self.assertIs(t.state, TimerState.RUNNING)
        clk.t += 71
        t.update(now)
        self.assertIs(t.state, TimerState.DONE)
        t.on_action(now)                                               # conferma
        self.assertEqual((t.state, t.shown_remaining()), (TimerState.IDLE, 120))


class TestAlarm(unittest.TestCase):
    def test_rings_once(self) -> None:
        a = AlarmWidget({"alarms": [{"time": "07:00", "days": [2]}]})  # mercoledì
        wed = datetime(2026, 9, 23, 7, 0, 10)
        a.update(wed)
        self.assertIsNotNone(a.alert())
        a.on_action(wed)
        self.assertIsNone(a.alert())
        a.update(wed)  # stesso minuto: non deve risuonare
        self.assertIsNone(a.alert())

    def test_not_on_other_days(self) -> None:
        a = AlarmWidget({"alarms": [{"time": "07:00", "days": [0]}]})
        a.update(datetime(2026, 9, 23, 7, 0))
        self.assertIsNone(a.alert())

    def test_next_alarm(self) -> None:
        a = AlarmWidget({"alarms": [{"time": "07:00", "days": [0, 1, 2, 3, 4]}]})
        nxt = a.next_alarm(datetime(2026, 9, 25, 8, 0))  # venerdì dopo le 7
        assert nxt is not None
        self.assertEqual(nxt[1], datetime(2026, 9, 28, 7, 0))  # lunedì


class TestLocation(unittest.TestCase):
    def _loc(self, mode: str, **extra: object) -> Any:
        from dash.location import Location
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        cfg = {"mode": mode, "name": "Ventotene", "lat": 40.796, "lon": 13.436, **extra}
        return Location(cfg, cache_dir=tmp.name)

    def test_fixed(self) -> None:
        loc = self._loc("fixed")
        self.assertFalse(loc.refresh(force=True))
        self.assertEqual(loc.snapshot(), ("Ventotene", 40.796, 13.436))

    def test_ip_fallback_to_second_service(self) -> None:
        from unittest import mock
        import urllib.error
        from dash import location as L
        answers = [urllib.error.URLError("giù"),
                   {"status": "success", "lat": 41.26, "lon": 13.61, "city": "Formia"}]

        def fake(url: str, timeout: float = 10) -> dict:
            a = answers.pop(0)
            if isinstance(a, Exception):
                raise a
            return a
        loc = self._loc("ip")
        with mock.patch.object(L, "_get_json", side_effect=fake):
            self.assertTrue(loc.refresh(force=True))
        self.assertEqual(loc.snapshot(), ("Formia", 41.26, 13.61))
        self.assertTrue(loc.source.startswith("ip:"))

    def test_ip_all_fail_keeps_fixed(self) -> None:
        from unittest import mock
        from dash import location as L
        loc = self._loc("ip")
        with mock.patch.object(L, "_get_json", return_value={"latitude": "Sign up to access"}):
            self.assertFalse(loc.refresh(force=True))
        self.assertEqual(loc.snapshot()[1:], (40.796, 13.436))

    @staticmethod
    def _nmea(body: str) -> str:
        check = 0
        for c in body:
            check ^= ord(c)
        return f"${body}*{check:02X}"

    def test_parse_nmea(self) -> None:
        from dash.location import parse_nmea
        rmc = self._nmea("GPRMC,101512.00,A,4112.8220,N,01334.2600,E,0.02,,270926,,,A")
        self.assertEqual(parse_nmea(rmc), (41.21370, 13.571))            # Gaeta
        gga = self._nmea("GNGGA,101512.00,4112.8220,N,01334.2600,E,1,08,1.0,5.0,M,45.0,M,,")
        self.assertEqual(parse_nmea(gga), (41.2137, 13.571))
        self.assertIsNone(parse_nmea(self._nmea("GPRMC,101512.00,V,,,,,,,270926,,,N")))  # no fix
        self.assertIsNone(parse_nmea(rmc[:-2] + "00"))                   # checksum sbagliato
        self.assertIsNone(parse_nmea("rumore"))

    def test_parse_nmcli(self) -> None:
        from dash.location import parse_nmcli
        text = "AA\\:BB\\:CC\\:DD\\:EE\\:FF:80\n11\\:22\\:33\\:44\\:55\\:66:30\n--:--\n"
        self.assertEqual(parse_nmcli(text), [
            {"macAddress": "aa:bb:cc:dd:ee:ff", "signalStrength": -60},
            {"macAddress": "11:22:33:44:55:66", "signalStrength": -85}])

    def test_auto_prefers_gps_then_wifi_then_ip(self) -> None:
        from unittest import mock
        from dash import location as L

        def fake(url: str, timeout: float = 10, body: dict | None = None) -> dict:
            if url.startswith(L.BEACONDB_URL):
                return {"location": {"lat": 41.2137, "lng": 13.5710}, "accuracy": 40}
            if url.startswith(L.REVERSE_URL):
                return {"address": {"town": "Gaeta"}}
            return {"status": "success", "lat": 41.62, "lon": 12.63, "city": "Lavinio"}

        aps = [{"macAddress": "aa:bb:cc:dd:ee:ff", "signalStrength": -60}] * 2
        loc = self._loc("auto")
        with mock.patch.object(L, "_from_gpsd", return_value=(41.25, 13.6)), \
                mock.patch.object(L, "_get_json", side_effect=fake):
            loc.refresh(force=True)
        self.assertEqual((loc.snapshot(), loc.kind()), (("Gaeta", 41.25, 13.6), "gps"))
        loc = self._loc("auto")
        with mock.patch.object(L, "_from_gpsd", return_value=None), \
                mock.patch.object(L, "_from_nmea_device", return_value=None), \
                mock.patch.object(L, "_scan_wifi", return_value=aps), \
                mock.patch.object(L, "_get_json", side_effect=fake):
            loc.refresh(force=True)
        self.assertEqual((loc.snapshot(), loc.kind()), (("Gaeta", 41.2137, 13.571), "wifi"))
        loc = self._loc("auto")
        with mock.patch.object(L, "_from_gpsd", return_value=None), \
                mock.patch.object(L, "_from_nmea_device", return_value=None), \
                mock.patch.object(L, "_scan_wifi", return_value=[]), \
                mock.patch.object(L, "_get_json", side_effect=fake):
            loc.refresh(force=True)
        self.assertEqual((loc.snapshot()[0], loc.kind()), ("Lavinio", "ip"))  # ultima risorsa

    def test_precise_position_without_a_name_drops_the_old_one(self) -> None:
        """Wi-Fi lontano dalle coordinate fisse e Nominatim giù: niente nome sbagliato."""
        from unittest import mock
        import urllib.error
        from dash import location as L

        def fake(url: str, timeout: float = 10, body: dict | None = None) -> dict:
            if url.startswith(L.BEACONDB_URL):
                return {"location": {"lat": 45.0, "lng": 9.0}}
            raise urllib.error.URLError("giù")

        loc = self._loc("auto")
        aps = [{"macAddress": "aa:bb:cc:dd:ee:ff", "signalStrength": -60}] * 2
        with mock.patch.object(L, "_from_gpsd", return_value=None), \
                mock.patch.object(L, "_from_nmea_device", return_value=None), \
                mock.patch.object(L, "_scan_wifi", return_value=aps), \
                mock.patch.object(L, "_get_json", side_effect=fake):
            loc.refresh(force=True)
        self.assertEqual(loc.snapshot(), ("", 45.0, 9.0))

    def test_city(self) -> None:
        from unittest import mock
        from dash import location as L
        loc = self._loc("city", city="Gaeta")
        res = {"results": [{"name": "Gaeta", "latitude": 41.21, "longitude": 13.57}]}
        with mock.patch.object(L, "_get_json", return_value=res):
            loc.refresh(force=True)
        self.assertEqual(loc.snapshot(), ("Gaeta", 41.21, 13.57))


class TestClockAndSystem(unittest.TestCase):
    def test_progress_modes(self) -> None:
        from dash.location import Location
        from dash.widgets.clock import ClockWidget
        loc = Location({"mode": "fixed", "lat": 40.796, "lon": 13.436})
        noon = datetime(2026, 9, 23, 12, 0)
        self.assertAlmostEqual(ClockWidget({"progress": "day"}, loc).progress(noon)[1], 0.5)
        self.assertAlmostEqual(ClockWidget({"progress": "hour"}, loc).progress(
            datetime(2026, 9, 23, 12, 30))[1], 0.5)
        _, f = ClockWidget({"progress": "daylight"}, loc).progress(datetime(2026, 9, 23, 3, 0))
        self.assertEqual(f, 0.0)

    def test_system_widget_samples(self) -> None:
        from dash.sysinfo import Stats
        from dash.widgets.system import SystemWidget

        class FakeSampler:
            def sample(self) -> Stats:
                return Stats(cpu=0.37, ram_used=2 * 1024 ** 3, ram_total=4 * 1024 ** 3,
                             disk_used=30 * 1024 ** 3, disk_total=58 * 1024 ** 3,
                             temp_c=51.2, uptime_s=90061, ip="192.168.1.20")
        w = SystemWidget({"sample_s": 60, "refresh_s": 60}, sampler=FakeSampler())  # type: ignore[arg-type]
        w.update(datetime.now())
        w.close()
        st, _ = w.snapshot()
        self.assertAlmostEqual(st.temp_c or 0, 51.2, places=1)

    def test_sampler_real(self) -> None:
        import time as _t
        from dash.sysinfo import Sampler
        s = Sampler()
        s.sample()
        _t.sleep(0.2)
        st = s.sample()
        self.assertIsNotNone(st.ram_frac)
        self.assertIsNotNone(st.disk_frac)
        if st.cpu is not None:
            self.assertTrue(0.0 <= st.cpu <= 1.0)


class TestAstro(unittest.TestCase):
    def test_sun_times_ventotene(self) -> None:
        """Riferimenti alpenglowapp.com (Europe/Rome, CEST = UTC+2), tolleranza 2 min."""
        from datetime import date, timedelta, timezone
        from dash.astro import _event_utc
        cest = timezone(timedelta(hours=2))
        cases = [(date(2026, 8, 5), True, "06:05"), (date(2026, 6, 8), True, "05:34"),
                 (date(2026, 8, 4), False, "20:18"), (date(2026, 6, 20), False, "20:41")]
        for d, rising, ref in cases:
            got = _event_utc(d, 40.796, 13.436, rising)
            assert got is not None
            ref_dt = datetime.combine(d, datetime.strptime(ref, "%H:%M").time(), cest)
            self.assertLessEqual(abs((got - ref_dt).total_seconds()), 120, (d, ref, got.astimezone(cest)))

    def test_polar_night(self) -> None:
        from datetime import date
        from dash.astro import sun_times
        self.assertEqual(sun_times(date(2026, 12, 21), 80.0, 15.0), (None, None))


class TestWeatherHelpers(unittest.TestCase):
    def test_beaufort(self) -> None:
        self.assertEqual(beaufort(0.4), 0)
        self.assertEqual(beaufort(14), 4)
        self.assertEqual(beaufort(35), 8)
        self.assertEqual(beaufort(70), 12)

    def test_directions(self) -> None:
        self.assertEqual(rosa(0), "N")
        self.assertEqual(rosa(315), "NW")
        self.assertEqual(vento_nome(135), "SCIROCCO")
        self.assertEqual(vento_nome(225), "LIBECCIO")

    def test_moon(self) -> None:
        # Luna piena del 7 settembre 2025 (eclissi totale), ~18:09 UTC.
        from datetime import timezone
        p = moon_phase(datetime(2025, 9, 7, 18, 9, tzinfo=timezone.utc))
        self.assertAlmostEqual(p, 0.5, delta=0.03)
        self.assertGreater(moon_illumination(p), 0.98)

    def test_describe_unknown(self) -> None:
        self.assertEqual(describe(0)[0], "SERENO")
        self.assertEqual(describe(1234)[1], "unknown")


class TestFramebufferAndTouch(unittest.TestCase):
    def test_pack_rgb565_and_xrgb(self) -> None:
        from dash.display.fb import pack
        img = Image.new("RGB", (2, 1))
        img.putpixel((0, 0), (255, 0, 0))
        img.putpixel((1, 0), (0, 0, 255))
        self.assertEqual(pack(img, 16), bytes([0x00, 0xF8, 0x1F, 0x00]))   # rosso, blu (LE)
        img2 = Image.new("RGB", (2, 1))
        img2.putpixel((0, 0), (1, 2, 3))
        img2.putpixel((1, 0), (4, 5, 6))
        self.assertEqual(pack(img2, 32), bytes([3, 2, 1, 255, 6, 5, 4, 255]))  # B G R X

    def test_framebuffer_display_writes(self) -> None:
        import tempfile
        from unittest import mock
        from dash.display import fb as FB
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sysd = root / "sys" / "fb1"
            sysd.mkdir(parents=True)
            (sysd / "name").write_text("ili9486drmfb\n")
            (sysd / "virtual_size").write_text("480,320\n")
            (sysd / "bits_per_pixel").write_text("16\n")
            (sysd / "stride").write_text("960\n")
            (root / "dev").mkdir()
            (root / "dev" / "fb1").write_bytes(bytes(480 * 320 * 2))
            with mock.patch.object(FB, "SYS_FB", root / "sys"), \
                    mock.patch.object(FB, "DEV_DIR", root / "dev"):
                d = FB.FramebufferDisplay("auto", "auto", {"console_off": False})
                self.assertEqual((d.width, d.height), (480, 320))
                d.show(Image.new("RGB", (480, 320), (0, 0, 0)))
                d.close()
            data = (root / "dev" / "fb1").read_bytes()
            self.assertEqual(len(data), 480 * 320 * 2)
            self.assertEqual(set(data), {0})  # schermo nero

    def test_framebuffer_writes_only_changed_rows(self) -> None:
        from unittest import mock
        from PIL import ImageDraw
        from dash.display import fb as FB
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sysd = root / "sys" / "fb1"
            sysd.mkdir(parents=True)
            for k, v in (("name", "ili9486drmfb"), ("virtual_size", "480,320"),
                         ("bits_per_pixel", "16"), ("stride", "960")):
                (sysd / k).write_text(v + "\n")
            (root / "dev").mkdir()
            (root / "dev" / "fb1").write_bytes(bytes(480 * 320 * 2))
            with mock.patch.object(FB, "SYS_FB", root / "sys"), \
                    mock.patch.object(FB, "DEV_DIR", root / "dev"):
                d = FB.FramebufferDisplay("auto", "auto", {"console_off": False})
                img = Image.new("RGB", (480, 320))
                d.show(img)
                writes: list[tuple[int, int]] = []
                real_seek, real_write = d._fh.seek, d._fh.write
                pos = {"at": 0}

                def seek(off: int, *a: int) -> int:
                    pos["at"] = off
                    return real_seek(off, *a)

                def write(data: bytes) -> int:
                    writes.append((pos["at"], len(data)))
                    return real_write(data)

                d._fh = mock.Mock(seek=seek, write=write, close=d._fh.close)
                img2 = img.copy()
                ImageDraw.Draw(img2).rectangle((100, 50, 120, 60), fill=(255, 255, 255))
                d.show(img2)
                d.show(img2)                                   # identico: nessuna scrittura
                d.close()
            self.assertEqual(writes, [(50 * 960, 11 * 960)])   # solo le righe 50…60
            data = (root / "dev" / "fb1").read_bytes()
            self.assertEqual(data[50 * 960 + 100 * 2: 50 * 960 + 100 * 2 + 2], b"\xff\xff")

    def test_find_touch_device(self) -> None:
        from dash.inputs import find_touch_device
        text = ('I: Bus=0000\nN: Name="vc4-hdmi"\nH: Handlers=kbd event0\n\n'
                'I: Bus=0000\nN: Name="ADS7846 Touchscreen"\nH: Handlers=mouse0 event1\n')
        self.assertEqual(find_touch_device(text), "/dev/input/event1")

    def test_calibration(self) -> None:
        from dash.inputs import ABS_X, ABS_Y, TouchCalibration
        cal = TouchCalibration({"x_min": 200, "x_max": 3900, "invert_y": True},
                               {ABS_X: (0, 4095), ABS_Y: (0, 4095)})
        t = cal.map(200, 0)
        self.assertEqual((t.x, t.y), (0.0, 1.0))

    def test_tap_from_samples_ignores_touchdown_and_lift_off(self) -> None:
        from dash.inputs import tap_from_samples
        samples = [(3900, 100), (2000, 1500), (2010, 1490), (1990, 1510), (2005, 1500),
                   (400, 3800), (4000, 0)]     # appoggio e distacco sballati, un salto nel mezzo
        self.assertEqual(tap_from_samples(samples), (2005, 1500))
        self.assertEqual(tap_from_samples([(10, 20)]), (10, 20))
        self.assertIsNone(tap_from_samples([]))

    def test_calibration_can_change_while_running(self) -> None:
        from dash.inputs import ABS_X, ABS_Y, TouchCalibration
        cal = TouchCalibration({}, {ABS_X: (0, 4095), ABS_Y: (0, 4095)})
        cal.apply({"x_min": 300, "x_max": 3800, "y_min": 200, "y_max": 3900, "swap_xy": True})
        t = cal.map(300, 3900)
        self.assertEqual((t.x, t.y, t.raw), (1.0, 0.0, (300, 3900)))

    def test_frame_and_panel_are_inverse(self) -> None:
        from dash.inputs import frame_to_panel, panel_to_frame
        for rot in (0, 90, 180, 270):
            fx, fy = panel_to_frame(*frame_to_panel(0.2, 0.7, rot), rot)
            self.assertAlmostEqual(fx, 0.2)
            self.assertAlmostEqual(fy, 0.7)

    def test_tap_just_outside_a_button_counts(self) -> None:
        """Un tocco a pochi pixel da un bottone vale per quello; lontano da tutti, per nessuno."""
        app = App(make_cfg(pages=[{"name": "Home", "widget": "clock"},
                                  {"name": "+", "widget": "new"}]),
                  MemDisplay(480, 320), queue.Queue())
        app.page_idx = 1
        b, hit = app.renderer.hit_boxes(app)[0]
        self.assertEqual(app.hit_at(b.x + 3, b.y - 5), hit)       # sopra la prima riga
        self.assertIsNone(app.hit_at(b.x + 3, b.y - 40))
        app.close()

    def _app(self, rotate: int = 0) -> App:
        cfg = make_cfg(display={"width": 480, "height": 320, "rotate": rotate})
        return App(cfg, MemDisplay(480, 320), queue.Queue())

    def test_tap_on_content_runs_the_action(self) -> None:
        """Tocco sul contenuto: avvia il timer; sulla linguetta: cambia pagina."""
        from dash.inputs import Tap
        from dash.widgets.timer import TimerState
        app = self._app()
        now = datetime(2026, 9, 23, 12, 0)
        app.page_idx = [p.name for p in app.pages].index("Timer")
        content = app.renderer.content_inner(app)
        app.handle_tap(Tap((content.x + content.w / 2) / 480, (content.y + content.h / 2) / 320), now)
        self.assertIs(app.widgets["timer"].state, TimerState.RUNNING)
        app.handle_tap(Tap((content.x + content.w / 2) / 480, (content.y + content.h / 2) / 320), now)
        self.assertIs(app.widgets["timer"].state, TimerState.PAUSED)
        before = app.widgets["timer"].remaining()
        b, hit = next(bh for bh in app.renderer.hit_boxes(app) if bh[1] == "add:300")
        app.handle_tap(Tap((b.x + b.w / 2) / 480, (b.y + b.h / 2) / 320), now)
        self.assertAlmostEqual(app.widgets["timer"].remaining(), before + 300)
        self.assertIs(app.widgets["timer"].state, TimerState.PAUSED)  # il bottone non avvia
        tab = app.renderer.nav_rows(app)[1]
        app.handle_tap(Tap((tab.x + tab.w / 2) / 480, (tab.y + tab.h / 2) / 320), now)
        self.assertEqual(app.page.name, "Meteo")

    def test_tap_rotation_matches_render(self) -> None:
        """Il tocco nel punto del pannello dove appare un pixel torna allo stesso punto del fotogramma."""
        for rot in (90, 180, 270):
            img = Image.new("1", (320, 480), 1)       # fotogramma verticale
            img.putpixel((40, 100), 0)
            panel = img.rotate(-rot, expand=True)    # come App.render
            bbox = ImageChops.invert(panel.convert("L")).getbbox()
            assert bbox is not None
            u, v = (bbox[0] + 0.5) / panel.width, (bbox[1] + 0.5) / panel.height
            fx, fy = {0: (u, v), 90: (v, 1 - u), 180: (1 - u, 1 - v), 270: (1 - v, u)}[rot]
            self.assertAlmostEqual(fx * 320, 40.5, delta=1.5, msg=f"rot {rot}")
            self.assertAlmostEqual(fy * 480, 100.5, delta=1.5, msg=f"rot {rot}")


class TestPages(unittest.TestCase):
    """Le pagine sono composte dal renderer: schedario a linguette e pannelli a colori."""

    def _app(self, w: int = 960, h: int = 540) -> App:
        cfg = make_cfg(display={"width": w, "height": h},
                       timer={"presets_s": [300], "labels": {"300": "pasta"}},
                       alarm={"alarms": [{"time": "06:30", "days": [0, 1, 2, 3, 4, 5, 6]}]})
        return App(cfg, MemDisplay(w, h), queue.Queue())

    def test_every_page_is_drawn_in_colour(self) -> None:
        for w, h in ((480, 320), (960, 540), (800, 480)):
            app = self._app(w, h)
            self.assertEqual([p.widget.name for p in app.pages],
                             ["clock", "weather", "timer", "alarm", "system", "new"])
            for i in range(len(app.pages)):
                app.page_idx = i
                img = app.render(datetime(2026, 9, 24, 7, 42))
                self.assertEqual((img.mode, img.size), ("RGB", (w, h)))
                colours = {c for _, c in (img.resize((80, 45)).getcolors(8192) or [])}
                self.assertGreater(len(colours), 3, f"pagina {app.page.name} senza pannelli")
            app.close()

    def test_one_tab_per_page_without_overlap(self) -> None:
        from dash.inputs import Tap
        app = self._app()
        tabs = app.renderer.nav_rows(app)
        self.assertEqual(len(tabs), len(app.pages))
        for a, b in zip(tabs, tabs[1:]):
            self.assertGreaterEqual(b.y, a.bottom - 1)
        for i in (2, 4, 0):
            t = tabs[i]
            app.handle_tap(Tap((t.x + t.w / 2) / 960, (t.y + t.h / 2) / 540),
                           datetime(2026, 9, 24, 7, 42))
            self.assertEqual(app.page_idx, i)
            tabs = app.renderer.nav_rows(app)
        app.close()

    def test_open_folder_is_attached_to_its_tab(self) -> None:
        """Il contenuto parte dalla linguetta aperta: niente stacco fra linguetta e cartella."""
        app = self._app()
        for i in range(len(app.pages)):
            app.page_idx = i
            lay = app.renderer.layout(960, 540, len(app.pages), i)
            self.assertEqual(lay.content.y, lay.tabs[i].bottom)
        app.close()

    def test_grid_is_legible_on_the_real_screen(self) -> None:
        """A 480×320 etichette ≥ 12 px, testi secondari ≥ 11 px, linguette ≥ 18 px anche con 6 pagine."""
        from dash.render.canvas import Canvas
        from dash.render.folders import layout
        cv = Canvas(Image.new("RGB", (480, 320)), {}, 1.0)
        self.assertGreaterEqual(cv.f_label.size, 12)
        self.assertGreaterEqual(cv.f_small.size, 11)
        lay = layout(480, 320, 6, 2)
        self.assertTrue(all(t.h >= 18 for t in lay.tabs))
        self.assertGreaterEqual(lay.content.h, 170)  # spazio utile anche con lo schedario pieno

    def test_rotation_keeps_frame_size(self) -> None:
        cfg = make_cfg(display={"width": 320, "height": 480, "rotate": 90})
        app = App(cfg, MemDisplay(480, 320), queue.Queue())
        self.assertEqual(app.render(datetime(2026, 9, 24, 7, 42)).size, (320, 480))
        app.close()


class TestLoop(unittest.TestCase):
    def test_draws_once_when_nothing_changes(self) -> None:
        # istante fisso e niente pagina sistema (cambia chiave ogni 2 s di orologio vero):
        # altrimenti il test dipende da quando gira, e sul Pi lento fallirebbe a caso
        disp = MemDisplay(480, 320)
        cfg = make_cfg(pages=[{"name": "Home", "widget": "clock"},
                              {"name": "Meteo", "widget": "weather"}])
        app = App(cfg, disp, queue.Queue())
        now = datetime(2026, 9, 24, 7, 42)
        app.step(now, 0.0, animate=False)
        app.step(now, 0.5, animate=False)  # stesso minuto, nessun evento
        self.assertEqual(len(disp.frames), 1)
        app.close()

    def test_page_change_redraws(self) -> None:
        disp = MemDisplay(480, 320)
        q: queue.Queue[Event] = queue.Queue()
        app = App(make_cfg(), disp, q)
        app.run(once=True)
        q.put(Event.NEXT)
        app.run(once=True)
        self.assertEqual(len(disp.frames), 2)
        self.assertEqual(app.page.name, "Meteo")
        app.close()


class TestPageEditing(unittest.TestCase):
    """Scheda "+": aggiunge e toglie pagine, e le salva in config.local.json."""

    def _app(self, tmp: str) -> App:
        main = Path(tmp) / "config.json"
        main.write_text(json.dumps({"pages": [{"name": "Home", "widget": "clock"},
                                              {"name": "+", "widget": "new"}]}), encoding="utf-8")
        cfg = make_cfg(pages=[{"name": "Home", "widget": "clock"}, {"name": "+", "widget": "new"}])
        return App(cfg, MemDisplay(480, 320), queue.Queue(), config_path=main)

    def test_catalogue_lists_only_the_optional_cards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            plus = app.pages[-1].widget
            self.assertEqual([v.label for v in plus.voci()], ["timer", "sveglia", "needle"])
            self.assertEqual({v.azione for v in plus.voci()}, {"add"})
            app.close()

    def test_entry_toggles_add_then_remove_and_saves(self) -> None:
        now = datetime(2026, 9, 24, 7, 42)
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            plus = app.pages[-1].widget
            plus.on_action(now)                       # prima voce: aggiunge il timer
            self.assertEqual([p.name for p in app.pages], ["Home", "Timer", "+"])
            self.assertEqual(app.page_idx, 1)         # si apre la pagina appena creata
            saved = json.loads((Path(tmp) / "config.local.json").read_text(encoding="utf-8"))
            self.assertEqual([p["widget"] for p in saved["pages"]], ["clock", "timer", "new"])
            self.assertEqual(plus.voci()[0].azione, "del")  # ora la stessa voce lo toglie
            app.page_idx = 2
            plus.on_action(now)
            self.assertEqual([p.name for p in app.pages], ["Home", "+"])
            self.assertIs(app.page.widget, plus)      # si resta sulla scheda "+"
            saved = json.loads((Path(tmp) / "config.local.json").read_text(encoding="utf-8"))
            self.assertEqual([p["widget"] for p in saved["pages"]], ["clock", "new"])
            app.close()

    def test_the_plus_card_cannot_remove_itself(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            app.pages[-1].widget.togli("new")
            self.assertEqual([p.name for p in app.pages], ["Home", "+"])
            app.close()

    def test_tap_on_a_chip_runs_it_at_once(self) -> None:
        """Un solo tocco sulla voce: la scheda si aggiunge subito, senza "seleziona e conferma"."""
        app = App(make_cfg(pages=[{"name": "Home", "widget": "clock"},
                                  {"name": "+", "widget": "new"}]),
                  MemDisplay(480, 320), queue.Queue())
        app.page_idx = 1
        boxes = [b for b, hit in app.renderer.hit_boxes(app) if hit.startswith("voce:")]
        self.assertEqual(len(boxes), len(app.pages[-1].widget.voci()))
        b = boxes[1]
        app.handle_tap(Tap((b.x + b.w / 2) / 480, (b.y + b.h / 2) / 320),
                       datetime(2026, 9, 24, 7, 42))
        self.assertEqual([p.widget.name for p in app.pages], ["clock", "alarm", "new"])
        app.close()


class TestNeedle(unittest.TestCase):
    """Scheda needle: stato del servizio, frasi inviate a /complete, risposta mostrata."""

    RISPOSTA = {"type": "call", "success": True, "error": None,
                "function_calls": [{"name": "get_weather", "arguments": {"city": "Ventotene"}}],
                "reasoning": "get_weather tool.", "confidence": 0.95}

    def _widget(self, post: Any, **cfg: Any) -> NeedleWidget:
        base = copy.deepcopy(DEFAULTS["needle"])
        base["regole"] = False     # qui si prova il modello: "meteo a ventotene" lo capirebbe il codice
        base.update(cfg)
        return NeedleWidget(base, clock=FakeClock(), post=post)

    @staticmethod
    def _wait(w: NeedleWidget) -> None:
        for _ in range(200):  # il thread della richiesta finisce in pochi millisecondi
            if not w.snapshot()[1]:
                return
            time.sleep(0.01)
        raise AssertionError("richiesta needle mai terminata")

    def test_parse_formats_the_recognised_call(self) -> None:
        r = parse_needle("meteo", self.RISPOSTA, 2210)
        self.assertEqual((r.chiamate, r.confidenza, r.ms, r.errore),
                         (("get_weather(city=Ventotene)",), 0.95, 2210, ""))
        vuota = parse_needle("boh", {"success": False, "error": "nessuna funzione",
                                     "function_calls": []}, 5)
        self.assertEqual((vuota.chiamate, vuota.errore), ((), "nessuna funzione"))

    def test_sends_reset_then_the_phrase_and_keeps_the_answer(self) -> None:
        chiamate: list[tuple[str, dict[str, Any]]] = []

        def post(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
            chiamate.append((url, payload))
            return self.RISPOSTA

        w = self._widget(post)
        w._online = True
        w.on_hit("q:0", datetime(2026, 9, 24, 7, 42))
        self._wait(w)
        self.assertEqual(chiamate, [("http://127.0.0.1:8090/reset", {}),
                                    ("http://127.0.0.1:8090/complete", {"input": "meteo a ventotene"})])
        online, busy, last = w.snapshot()
        self.assertEqual((online, busy, last.chiamate), (True, False, ("get_weather(city=Ventotene)",)))
        self.assertEqual(w.stato(), "pronto")
        self.assertEqual(w.flashing(), 0)                                     # bottone in rosa un attimo

    def test_offline_service_is_reported_and_not_called(self) -> None:
        def post(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
            raise AssertionError("il servizio è spento: non si deve chiamare")

        w = self._widget(post)
        w._online = False
        w.on_action(datetime(2026, 9, 24, 7, 42))
        self.assertEqual((w.stato(), w.snapshot()[1]), ("offline", False))

    def test_network_error_marks_the_service_offline(self) -> None:
        def post(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
            raise OSError("connessione rifiutata")

        w = self._widget(post)
        w._online = True
        w.on_action(datetime(2026, 9, 24, 7, 42))
        self._wait(w)
        online, _, last = w.snapshot()
        self.assertFalse(online)
        self.assertEqual(last.errore, "servizio non risponde")

    def test_back_cycles_through_the_phrases(self) -> None:
        w = self._widget(lambda *a: {})
        for atteso in (1, 2, 3, 0):
            w.on_back(datetime(2026, 9, 24, 7, 42))
            self.assertEqual(w.idx, atteso)

    def test_page_draws_and_exposes_one_button_per_phrase(self) -> None:
        cfg = make_cfg(pages=[{"name": "Home", "widget": "clock"},
                              {"name": "Needle", "widget": "needle"}])
        app = App(cfg, MemDisplay(480, 320), queue.Queue())
        app.page_idx = 1
        w = app.page.widget
        w.load_demo()
        img = app.render(datetime(2026, 9, 24, 7, 42))
        self.assertEqual(img.size, (480, 320))
        boxes = [b for b, hit in app.renderer.hit_boxes(app) if hit.startswith("q:")]
        self.assertEqual(len(boxes), len(w.queries))
        self.assertTrue(all(b.h >= 24 for b in boxes), "bottoni troppo bassi per il dito")
        app.close()

    def test_config_rejects_a_bad_url_or_empty_phrases(self) -> None:
        for bad in ({"url": "https://x"}, {"queries": []}, {"queries": ["a"] * 7},
                    {"soglia": 1.5}, {"soglia_pagine": "bassa"}, {"soglia_luci": -1}):
            with self.assertRaises(ConfigError):
                validate(make_cfg(needle=bad), WIDGET_NAMES)

    def test_service_files_are_consistent(self) -> None:
        """tools.json valido e il file del servizio punta alla stessa porta della config."""
        radice = Path(__file__).parent.parent
        tools = json.loads((radice / "needle" / "tools.json").read_text(encoding="utf-8"))
        self.assertTrue(all({"name", "description", "parameters"} <= set(t) for t in tools))
        # il modello può proporre solo ciò che il dashboard sa eseguire, e viceversa
        # (l'interprete di frasi ne usa altre, che il modello non conosce: `SOLO_REGOLE`)
        self.assertEqual({t["name"] for t in tools} | azioni.SOLO_REGOLE, set(azioni.AZIONI))
        self.assertFalse({t["name"] for t in tools} & azioni.SOLO_REGOLE)
        unit = (radice / "systemd" / "needle.service").read_text(encoding="utf-8")
        porta = DEFAULTS["needle"]["url"].rsplit(":", 1)[1]
        self.assertIn(f"--serve --port {porta}", unit)
        self.assertIn("/home/pi/pi-dash/needle/tools.json", unit)  # lo script sostituisce il percorso


class TestNeedleActions(unittest.TestCase):
    """Le funzioni riconosciute da Needle diventano azioni del dashboard, con argomenti controllati."""

    NOW = datetime(2026, 9, 24, 7, 42)

    def _app(self, tmp: str, pages: list[dict[str, str]] | None = None, **needle: Any) -> App:
        main = Path(tmp) / "config.json"
        main.write_text("{}", encoding="utf-8")
        cfg = make_cfg(pages=pages or [{"name": "Home", "widget": "clock"},
                                       {"name": "+", "widget": "new"}], needle=needle)
        return App(cfg, MemDisplay(480, 320), queue.Queue(), config_path=main)

    def _saved(self, tmp: str) -> dict[str, Any]:
        return json.loads((Path(tmp) / "config.local.json").read_text(encoding="utf-8"))

    def test_start_timer_creates_the_page_and_runs_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            self.assertEqual(azioni.esegui(app, "start_timer_minutes", {"minutes": 5}),
                             "timer 5' avviato")
            timer = app.find_page("timer")
            assert timer is not None
            self.assertIs(timer.widget.state, TimerState.RUNNING)
            self.assertEqual(timer.widget.shown_remaining(), 300)
            self.assertIs(app.page, timer)                                  # si apre la pagina
            self.assertEqual([p["widget"] for p in self._saved(tmp)["pages"]],
                             ["clock", "timer", "new"])                     # e resta al riavvio
            app.close()

    def test_without_navigation_the_current_page_stays_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            start = app.page
            azioni.esegui(app, "start_timer_minutes", {"minutes": 2.5}, naviga=False)
            self.assertIs(app.page, start)
            timer = app.find_page("timer")
            assert timer is not None
            self.assertEqual(timer.widget.shown_remaining(), 150)
            app.close()

    def test_seconds_and_minutes_are_separate_functions(self) -> None:
        """Il modello copia il numero senza convertire: l'unità la decide la funzione scelta."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            self.assertEqual(azioni.esegui(app, "start_timer_seconds", {"seconds": 90}),
                             "timer 1'30\" avviato")
            timer = app.find_page("timer")
            assert timer is not None
            self.assertEqual(timer.widget.shown_remaining(), 90)
            self.assertEqual(azioni.esegui(app, "start_timer_seconds", {"seconds": 30}),
                             "timer 30\" avviato")
            self.assertEqual(timer.widget.shown_remaining(), 30)                # sostituisce
            self.assertEqual(azioni.esegui(app, "start_timer_minutes", {"minutes": 1.5}),
                             "timer 1'30\" avviato")
            app.close()

    def test_set_alarm_adds_saves_and_does_not_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            self.assertEqual(azioni.esegui(app, "set_alarm", {"time": "7:30"}),
                             "sveglia 07:30 ogni giorno")
            azioni.esegui(app, "set_alarm", {"time": "07:30"})
            alarm = app.find_page("alarm")
            assert alarm is not None
            self.assertEqual(len(alarm.widget.alarms), 1)
            self.assertEqual(self._saved(tmp)["alarm"]["alarms"],
                             [{"time": "07:30", "days": [0, 1, 2, 3, 4, 5, 6], "enabled": True}])
            app.close()

    def test_bad_arguments_change_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            for nome, args in (("start_timer_minutes", {"minutes": 0}),
                               ("start_timer_minutes", {"minutes": -3}),
                               ("start_timer_minutes", {"minutes": "boh"}),
                               ("start_timer_minutes", {}),
                               ("start_timer_minutes", {"minutes": float("nan")}),
                               ("start_timer_minutes", {"minutes": 1000}),
                               ("start_timer_seconds", {"seconds": 0}),
                               ("start_timer_seconds", {"seconds": 0.2}),
                               ("set_alarm", {"time": "25:00"}), ("set_alarm", {"time": "mattina"}),
                               ("set_alarm", {}), ("open_timer", {})):
                self.assertTrue(azioni.esegui(app, nome, args).startswith("errore"), (nome, args))
            self.assertEqual([p.kind for p in app.pages], ["clock", "new"])  # nessuna pagina creata
            self.assertFalse((Path(tmp) / "config.local.json").exists())
            app.close()

    def test_open_functions_open_only_existing_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            self.assertEqual(azioni.esegui(app, "open_settings", {}), "apro impostazioni")
            self.assertEqual(app.page.kind, "new")
            self.assertEqual(azioni.esegui(app, "open_home", {}), "apro home")
            self.assertEqual(app.page.kind, "clock")
            self.assertEqual(azioni.esegui(app, "open_timer", {}),
                             "errore: pagina timer non presente")
            self.assertEqual(azioni.esegui(app, "spegni", {}), "funzione non prevista: spegni")
            self.assertEqual(azioni.esegui(app, "poweroff", {}), "funzione non prevista: poweroff")
            app.close()

    def _needle_app(self, tmp: str, confidenza: float, calls: list[dict[str, Any]] | None = None,
                    **needle: Any) -> tuple[App, NeedleWidget]:
        needle.setdefault("regole", False)    # queste prove sono sul percorso del modello
        app = self._app(tmp, [{"name": "Home", "widget": "clock"},
                              {"name": "Needle", "widget": "needle"},
                              {"name": "+", "widget": "new"}], **needle)
        app.page_idx = 1
        w = app.page.widget
        assert isinstance(w, NeedleWidget)
        w.load_demo()  # servizio "acceso" e nessun controllo di rete durante il test
        chiamate = calls or [{"name": "start_timer_minutes", "arguments": {"minutes": 5}}]
        w._post = lambda url, payload, timeout: (
            {} if url.endswith("/reset") else
            {"success": True, "confidence": confidenza, "function_calls": chiamate})
        return app, w

    def test_recognised_call_runs_in_the_main_loop_and_reports_the_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app, w = self._needle_app(tmp, 0.95)
            w.ask(1)
            TestNeedle._wait(w)
            self.assertIsNone(app.find_page("timer"))         # il thread non tocca il dashboard
            app.step(self.NOW, 0.0, animate=False)
            self.assertIsNotNone(app.find_page("timer"))
            self.assertEqual(app.page.kind, "timer")
            self.assertEqual(w.snapshot()[2].esito, "timer 5' avviato")
            app.step(self.NOW, 0.5, animate=False)           # niente esecuzioni doppie
            self.assertEqual(len([p for p in app.pages if p.kind == "timer"]), 1)
            app.close()

    def test_low_confidence_is_not_executed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app, w = self._needle_app(tmp, 0.3)
            w.ask(1)
            TestNeedle._wait(w)
            app.step(self.NOW, 0.0, animate=False)
            self.assertIsNone(app.find_page("timer"))
            self.assertEqual(w.snapshot()[2].esito, "confidenza bassa: non eseguo")
            app.close()

    def test_opening_a_page_needs_less_confidence_than_changing_state(self) -> None:
        """Sbagliare pagina costa un tocco, sbagliare un timer o una sveglia no."""
        with tempfile.TemporaryDirectory() as tmp:
            app, w = self._needle_app(tmp, 0.4, calls=[
                {"name": "start_timer_minutes", "arguments": {"minutes": 5}},
                {"name": "open_home", "arguments": {}}])
            w.ask(0)
            TestNeedle._wait(w)
            app.step(self.NOW, 0.0, animate=False)
            self.assertIsNone(app.find_page("timer"))                  # 0,4 < 0,6: non si esegue
            self.assertEqual((app.page.kind, w.snapshot()[2].esito), ("clock", "apro home"))
            app.close()

    def test_execution_can_be_turned_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app, w = self._needle_app(tmp, 0.95, esegui=False)
            w.ask(1)
            TestNeedle._wait(w)
            app.step(self.NOW, 0.0, animate=False)
            self.assertIsNone(app.find_page("timer"))
            self.assertEqual(w.snapshot()[2].esito, "")
            app.close()


LUCI_HUE: dict[str, Any] = {i: {"state": {"reachable": r}} for i, r in
                            (("1", False), ("5", True), ("7", True), ("11", True), ("14", False),
                             ("15", False), ("16", False))}
GRUPPI_HUE: dict[str, Any] = {
    "1": {"name": "Corridoio Gaeta", "type": "Room", "lights": ["1"]},
    "2": {"name": "Soggiorno", "type": "Room", "lights": ["15", "16"]},
    "6": {"name": "Corridoio", "type": "Room", "lights": ["11"]},
    "7": {"name": "Tenda", "type": "Room", "lights": ["7", "5"]},
    "10": {"name": "Terrazza", "type": "Room", "lights": ["14"]},
    "20": {"name": "Zona notte", "type": "Zone", "lights": ["5"]},   # le zone non sono stanze
}


class BridgeFinto:
    """Bridge Hue di prova: registra le chiamate e risponde come l'API v1."""

    def __init__(self, gruppi: dict[str, Any] | None = None, risposta_put: Any = None) -> None:
        self.gruppi = GRUPPI_HUE if gruppi is None else gruppi
        self.risposta_put = risposta_put
        self.chiamate: list[tuple[str, str, Any]] = []

    def __call__(self, metodo: str, percorso: str, corpo: dict[str, Any] | None) -> Any:
        self.chiamate.append((metodo, percorso, corpo))
        if percorso == "lights":
            return LUCI_HUE
        if percorso == "groups":
            return self.gruppi
        if self.risposta_put is not None:
            return self.risposta_put
        return [{"success": {f"/{percorso}/on": (corpo or {}).get("on")}}]

    def put(self) -> list[tuple[str, str, Any]]:
        return [c for c in self.chiamate if c[0] == "PUT"]


class TestHue(unittest.TestCase):
    """Luci Philips Hue: stanze del bridge, comandi, registrazione, chiave al sicuro."""

    def _hue(self, bridge: BridgeFinto | None = None, **cfg: Any) -> tuple[Hue, BridgeFinto]:
        b = bridge or BridgeFinto()
        return Hue({"bridge": "192.168.1.73", "key": "SEGRETO", **cfg}, send=b, clock=FakeClock()), b

    def test_rooms_are_read_with_reachable_lights(self) -> None:
        hue, _ = self._hue()
        stanze = {s.nome: (s.luci, s.raggiungibili) for s in hue.stanze()}
        self.assertEqual(stanze, {"Corridoio Gaeta": (1, 0), "Soggiorno": (2, 0), "Corridoio": (1, 1),
                                  "Tenda": (2, 2), "Terrazza": (1, 0)})   # solo le stanze, non le zone

    def test_room_names_are_matched_without_guessing(self) -> None:
        hue, _ = self._hue()
        for detto, atteso in (("soggiorno", "Soggiorno"), ("la luce del Soggiorno", "Soggiorno"),
                              ("TERRAZZA", "Terrazza"), ("corridoio", "Corridoio"),   # esatta, non ambigua
                              ("corridoio gaeta", "Corridoio Gaeta"), ("gaeta", "Corridoio Gaeta")):
            stanza = hue.trova(detto)
            assert stanza is not None
            self.assertEqual(stanza.nome, atteso, detto)
        for tutte in ("tutte", "tutte le luci", "", "  ", "casa"):
            self.assertIsNone(hue.trova(tutte), tutte)
        with self.assertRaises(HueError) as sconosciuta:
            hue.trova("cucina")
        self.assertEqual(str(sconosciuta.exception), "stanza sconosciuta: cucina")
        doppia = dict(GRUPPI_HUE, **{"30": {"name": "Camera Gaeta", "type": "Room", "lights": []}})
        hue2, _ = self._hue(BridgeFinto(doppia))
        with self.assertRaises(HueError) as ambigua:
            hue2.trova("gaeta")                                      # due stanze: non si indovina
        self.assertIn("ambigua", str(ambigua.exception))

    def test_rooms_are_cached_for_five_minutes(self) -> None:
        b = BridgeFinto()
        clock = FakeClock()
        hue = Hue({"bridge": "x", "key": "y"}, send=b, clock=clock)
        hue.stanze()
        hue.stanze()
        self.assertEqual([c[1] for c in b.chiamate], ["lights", "groups"])   # una sola lettura
        clock.t += 301
        hue.stanze()
        self.assertEqual(len(b.chiamate), 4)

    def test_commands_go_to_the_room_or_to_all_lights(self) -> None:
        hue, b = self._hue()
        soggiorno = hue.trova("soggiorno")
        hue.imposta(soggiorno, False)
        hue.imposta(None, True)
        hue.imposta(soggiorno, True, 50)
        hue.imposta(soggiorno, True, 100)
        hue.imposta(soggiorno, True, 1)
        self.assertEqual(b.put(), [("PUT", "groups/2/action", {"on": False}),
                                   ("PUT", "groups/0/action", {"on": True}),
                                   ("PUT", "groups/2/action", {"on": True, "bri": 127}),
                                   ("PUT", "groups/2/action", {"on": True, "bri": 254}),
                                   ("PUT", "groups/2/action", {"on": True, "bri": 3})])

    def test_bridge_errors_become_readable_messages(self) -> None:
        hue, _ = self._hue(BridgeFinto(risposta_put=[{"error": {"description": "unauthorized user"}}]))
        with self.assertRaises(HueError) as put:
            hue.imposta(None, True)
        self.assertEqual(str(put.exception), "bridge: unauthorized user")
        rifiutata = Hue({"bridge": "x", "key": "y"}, send=lambda m, p, c: [{"error": {}}])
        with self.assertRaises(HueError) as chiave:
            rifiutata.stanze()
        self.assertEqual(str(chiave.exception), "chiave rifiutata dal bridge")

    def test_a_moved_bridge_is_found_again_and_remembered(self) -> None:
        b = BridgeFinto()
        visti: list[str] = []
        salvati: list[str] = []

        def fabbrica(bridge: str, key: str, timeout: float) -> Any:
            visti.append(bridge)
            return b

        def vecchio(metodo: str, percorso: str, corpo: Any) -> Any:
            raise HueError("bridge non risponde")

        clock = FakeClock()
        hue = Hue({"bridge": "192.168.1.73", "key": "SEGRETO"}, send=vecchio, clock=clock,
                  ritrova=lambda: "192.168.1.99", fabbrica=fabbrica, on_trovato=salvati.append)
        self.assertEqual(hue.trova("soggiorno").nome, "Soggiorno")   # type: ignore[union-attr]
        self.assertEqual((hue.bridge, salvati), ("192.168.1.99", ["192.168.1.99"]))

    def test_bridge_search_does_not_repeat_and_ignores_foreign_bridges(self) -> None:
        chiamate: list[int] = []

        def vecchio(metodo: str, percorso: str, corpo: Any) -> Any:
            raise HueError("bridge non risponde")

        def ritrova() -> str:
            chiamate.append(1)
            return "10.0.0.5"

        altro = lambda b, k, t: (lambda m, p, c: [{"error": {}}])   # chiave rifiutata: non è il nostro
        clock = FakeClock()
        hue = Hue({"bridge": "192.168.1.73", "key": "k"}, send=vecchio, clock=clock,
                  ritrova=ritrova, fabbrica=altro)
        for _ in range(2):
            with self.assertRaises(HueError):
                hue.imposta(None, True)
        self.assertEqual((len(chiamate), hue.bridge), (1, "192.168.1.73"))   # pausa di un minuto
        clock.t += 61
        with self.assertRaises(HueError):
            hue.imposta(None, True)
        self.assertEqual(len(chiamate), 2)

    def test_the_key_never_appears_in_errors(self) -> None:
        from dash.hue import http_send
        with self.assertRaises(HueError) as err:
            http_send("127.0.0.1:1", "SEGRETO", 0.5)("GET", "lights", None)   # porta chiusa
        self.assertNotIn("SEGRETO", str(err.exception))
        self.assertIsNone(err.exception.__cause__)      # la catena degli errori conterrebbe l'URL
        self.assertTrue(err.exception.__suppress_context__)

    # --- azioni di Needle -------------------------------------------------
    def _app(self, hue: Hue) -> App:
        app = App(make_cfg(), MemDisplay(480, 320), queue.Queue())
        app.hue = hue
        return app

    def test_needle_lights_functions(self) -> None:
        hue, b = self._hue()
        app = self._app(hue)
        start = app.page
        esegui = lambda nome, args, frase: azioni.esegui(app, nome, args, frase=frase)  # noqa: E731
        self.assertEqual(esegui("lights_off", {"room": "soggiorno"}, "spegni il soggiorno"),
                         "luci Soggiorno spente (non raggiungibili)")   # 15 e 16 non rispondono
        self.assertEqual(esegui("lights_on", {"room": "tenda"}, "accendi la tenda"), "luci Tenda accese")
        self.assertEqual(esegui("lights_on", {"room": "tutte"}, "accendi tutte le luci"),
                         "tutte le luci accese")
        self.assertEqual(esegui("set_brightness", {"room": "tenda", "percent": 40}, "tenda al 40%"),
                         "luci Tenda al 40%")
        self.assertEqual([p[1:] for p in b.put()],
                         [("groups/2/action", {"on": False}), ("groups/7/action", {"on": True}),
                          ("groups/0/action", {"on": True}),
                          ("groups/7/action", {"on": True, "bri": 102})])
        self.assertIs(app.page, start)                            # le luci non cambiano pagina
        app.close()

    def test_the_verb_of_the_sentence_decides_on_or_off(self) -> None:
        """Il modello sceglie lights_off per "accendi tutte le luci": il verbo detto ha l'ultima parola."""
        hue, b = self._hue()
        app = self._app(hue)
        esegui = lambda nome, frase: azioni.esegui(app, nome, {"room": "tutte"}, frase=frase)  # noqa: E731
        self.assertEqual(esegui("lights_off", "accendi tutte le luci"), "tutte le luci accese")
        self.assertEqual(esegui("lights_on", "Spegni tutte le luci"), "tutte le luci spente")
        self.assertEqual(esegui("lights_on", "attiva la luce"), "tutte le luci accese")
        self.assertEqual(esegui("lights_on", "disattiva la luce"), "tutte le luci spente")
        self.assertEqual([p[2] for p in b.put()], [{"on": True}, {"on": False}, {"on": True}, {"on": False}])
        for frase in ("non accendere la luce", "spegni ma non il soggiorno", "luce del soggiorno", "",
                      "accendi e spegni il soggiorno", "senza luce"):
            self.assertTrue(esegui("lights_on", frase).startswith("errore"), frase)
        self.assertEqual(len(b.put()), 4)                        # i rifiuti non toccano il bridge
        app.close()

    def test_turning_on_with_a_level_in_the_sentence_sets_the_brightness(self) -> None:
        """"accendi il soggiorno al 100%" → il modello dà lights_off e perde il livello: lo legge il testo."""
        hue, b = self._hue()
        app = self._app(hue)
        soggiorno = {"room": "soggiorno"}
        for nome, frase, atteso, corpo in (
                ("lights_off", "accendi il soggiorno al 100%", "luci Soggiorno accese al 100% (non raggiungibili)",
                 {"on": True, "bri": 254}),
                ("lights_on", "accendi il soggiorno al 100 per cento", "luci Soggiorno accese al 100% (non raggiungibili)",
                 {"on": True, "bri": 254}),
                ("lights_on", "Accendi il soggiorno al massimo", "luci Soggiorno accese al 100% (non raggiungibili)",
                 {"on": True, "bri": 254}),
                ("lights_on", "accendi il soggiorno al 50%", "luci Soggiorno accese al 50% (non raggiungibili)",
                 {"on": True, "bri": 127}),
                ("lights_on", "accendi il soggiorno", "luci Soggiorno accese (non raggiungibili)", {"on": True})):
            self.assertEqual(azioni.esegui(app, nome, soggiorno, frase=frase), atteso, frase)
            self.assertEqual(b.put()[-1][2], corpo, frase)
        # spegnere non ha livello; un livello fuori scala o una negazione non si eseguono
        self.assertEqual(azioni.esegui(app, "lights_off", soggiorno, frase="spegni il soggiorno al 100%"),
                         "luci Soggiorno spente (non raggiungibili)")
        self.assertEqual(b.put()[-1][2], {"on": False})
        n = len(b.put())
        self.assertEqual(azioni.esegui(app, "lights_on", soggiorno, frase="accendi il soggiorno al 150%"),
                         "errore: luminosità da 1 a 100")
        self.assertEqual(azioni.esegui(app, "lights_on", soggiorno, frase="accendi il soggiorno al 0%"),
                         "errore: luminosità da 1 a 100")
        self.assertTrue(azioni.esegui(app, "lights_on", soggiorno,
                                      frase="non accendere il soggiorno al massimo").startswith("errore"))
        self.assertEqual(len(b.put()), n)                        # nessun rifiuto tocca il bridge
        app.close()

    def test_brightness_must_be_written_in_the_sentence(self) -> None:
        hue, b = self._hue()
        app = self._app(hue)
        args = {"room": "tenda", "percent": 50}
        self.assertEqual(azioni.esegui(app, "set_brightness", args, frase="tenda al 50 per cento"),
                         "luci Tenda al 50%")
        self.assertEqual(azioni.esegui(app, "set_brightness", args, frase="abbassa la tenda"),
                         "errore: 50% non è nella frase: non eseguo")           # numero inventato
        self.assertEqual(azioni.esegui(app, "set_brightness", args, frase="tenda al 500"),
                         "errore: 50% non è nella frase: non eseguo")           # 500 non è 50
        self.assertEqual(len(b.put()), 1)
        app.close()

    def test_needle_lights_refuse_bad_input_without_touching_the_bridge(self) -> None:
        hue, b = self._hue()
        app = self._app(hue)
        for nome, args, frase, msg in (
                ("set_brightness", {"room": "tenda", "percent": 0}, "tenda a 0", "luminosità da 1 a 100"),
                ("set_brightness", {"room": "tenda", "percent": 101}, "tenda a 101", "luminosità da 1 a 100"),
                ("set_brightness", {"room": "tenda", "percent": "tanto"}, "tenda tanto", "luminosità non valida"),
                ("set_brightness", {"room": "tenda"}, "tenda", "luminosità non valida"),
                ("set_brightness", {"room": "tenda", "percent": float("inf")}, "tenda", "luminosità non valida"),
                ("lights_on", {"room": "cucina"}, "accendi la cucina", "stanza sconosciuta: cucina")):
            self.assertEqual(azioni.esegui(app, nome, args, frase=frase), f"errore: {msg}", (nome, args))
        self.assertEqual(b.put(), [])
        app.close()

    def test_needle_lights_need_a_configured_bridge_and_report_a_dead_one(self) -> None:
        app = self._app(Hue({}))
        self.assertEqual(azioni.esegui(app, "lights_on", {"room": "tenda"}, frase="accendi la tenda"),
                         "errore: hue non configurato (--hue-registra)")
        app.close()

        def morto(metodo: str, percorso: str, corpo: Any) -> Any:
            raise HueError("bridge non risponde")

        app = self._app(Hue({"bridge": "x", "key": "y"}, send=morto))
        self.assertEqual(azioni.esegui(app, "lights_off", {"room": "tenda"}, frase="spegni la tenda"),
                         "errore: bridge non risponde")
        app.close()

    def test_each_kind_of_function_has_its_own_confidence_threshold(self) -> None:
        from dash.azioni import categoria
        self.assertEqual({categoria(n) for n in ("lights_on", "lights_off", "set_brightness")}, {"luci"})
        self.assertEqual({categoria(n) for n in ("open_home", "get_weather")}, {"pagina"})
        self.assertEqual({categoria(n) for n in ("start_timer_minutes", "set_alarm", "boh")}, {"stato"})

    # --- registrazione e permessi ------------------------------------------
    def test_registration_waits_for_the_link_button(self) -> None:
        risposte = iter([[{"error": {"description": "link button not pressed"}}]] * 2
                        + [[{"success": {"username": "CHIAVE"}}]])
        clock = FakeClock()
        chiamate: list[Any] = []

        def send(metodo: str, percorso: str, corpo: Any) -> Any:
            chiamate.append((metodo, percorso, corpo))
            return next(risposte)

        chiave = registra("x", send, attesa_s=30, clock=clock, pausa=lambda s: setattr(clock, "t", clock.t + s))
        self.assertEqual((chiave, len(chiamate)), ("CHIAVE", 3))
        self.assertEqual(chiamate[0], ("POST", "", {"devicetype": "pidash#raspberry"}))

    def test_registration_gives_up_and_reports_other_errors(self) -> None:
        clock = FakeClock()
        premi = lambda m, p, c: [{"error": {"description": "link button not pressed"}}]
        with self.assertRaises(HueError):
            registra("x", premi, attesa_s=5, clock=clock,
                     pausa=lambda s: setattr(clock, "t", clock.t + s))         # tasto mai premuto
        with self.assertRaises(HueError) as altro:
            registra("x", lambda m, p, c: [{"error": {"description": "rate limit"}}], attesa_s=5, clock=clock)
        self.assertEqual(str(altro.exception), "rate limit")

    def test_registration_command_saves_the_key_privately(self) -> None:
        import contextlib
        import io
        import os
        from dash.main import registra_hue
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp) / "config.json"
            main.write_text("{}", encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                codice = registra_hue("192.168.1.73", main,
                                      lambda m, p, c: [{"success": {"username": "CHIAVE-SEGRETA"}}])
            self.assertEqual(codice, 0)
            self.assertNotIn("CHIAVE-SEGRETA", out.getvalue())               # mai a video
            local = Path(tmp) / "config.local.json"
            self.assertEqual(json.loads(local.read_text(encoding="utf-8"))["hue"],
                             {"bridge": "192.168.1.73", "key": "CHIAVE-SEGRETA"})
            if os.name != "nt":
                self.assertEqual(local.stat().st_mode & 0o777, 0o600)

    def test_saving_settings_keeps_the_permissions_of_the_local_file(self) -> None:
        import os
        from dash.config import save_local
        if os.name == "nt":
            self.skipTest("permessi POSIX")
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp) / "config.json"
            main.write_text("{}", encoding="utf-8")
            local = Path(tmp) / "config.local.json"
            local.write_text('{"hue": {"key": "k"}}', encoding="utf-8")
            local.chmod(0o600)
            save_local(main, {"backlight": {"level": 40}})                   # come fa il dashboard
            self.assertEqual(local.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(local.read_text(encoding="utf-8"))["hue"], {"key": "k"})

    def test_hue_config_is_validated(self) -> None:
        for bad in ({"bridge": 1}, {"key": None}, {"timeout_s": 0}, {"timeout_s": 99}):
            with self.assertRaises(ConfigError):
                validate(make_cfg(hue=bad), WIDGET_NAMES)


class TestSettings(unittest.TestCase):
    """Impostazioni: luminosità, calibrazione del touch, spegnimento con conferma."""

    def _app(self, tmp: str) -> App:
        main = Path(tmp) / "config.json"
        main.write_text("{}", encoding="utf-8")
        cfg = make_cfg(pages=[{"name": "Home", "widget": "clock"}, {"name": "+", "widget": "new"}])
        app = App(cfg, MemDisplay(480, 320), queue.Queue(), config_path=main)
        app.page_idx = 1
        return app

    def _tap(self, app: App, hit: str) -> None:
        b = next(bx for bx, h in app.renderer.hit_boxes(app) if h == hit)
        app.handle_tap(Tap((b.x + b.w / 2) / 480, (b.y + b.h / 2) / 320),
                       datetime(2026, 9, 24, 7, 42))

    def test_brightness_is_clamped_saved_and_dims_the_frame(self) -> None:
        now = datetime(2026, 9, 24, 7, 42)
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            self.assertTrue(app.backlight.software)             # nel simulatore mai il LED vero
            bright = app.step(now, 0.0, animate=False)
            for _ in range(12):
                self._tap(app, "luce:-10")
            self.assertEqual(app.backlight.level, 10)           # mai sotto il 10 %
            dim = app.step(now, 0.1, animate=False)
            self.assertIsNotNone(dim)
            self.assertLess(sum(dim.convert("L").getdata()), sum(bright.convert("L").getdata()) / 5)
            saved = json.loads((Path(tmp) / "config.local.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["backlight"], {"level": 10})
            app.close()

    def test_hardware_backlight_from_sysfs(self) -> None:
        from dash.backlight import Backlight
        with tempfile.TemporaryDirectory() as tmp:
            dev = Path(tmp) / "backlight0"
            dev.mkdir()
            (dev / "max_brightness").write_text("255\n")
            (dev / "brightness").write_text("255\n")
            bl = Backlight(50, "auto", Path(tmp))
            self.assertTrue(bl.hardware)
            self.assertEqual((dev / "brightness").read_text().strip(), "128")
            img = Image.new("RGB", (2, 2), (200, 200, 200))
            self.assertIs(bl.apply(img), img)                   # col LED vero niente ritocchi
            (dev / "max_brightness").write_text("1\n")         # solo acceso/spento
            bl = Backlight(50, "auto", Path(tmp))
            self.assertTrue(bl.software)
            self.assertEqual(bl.apply(img).getpixel((0, 0)), (100, 100, 100))

    def test_calibration_from_four_taps(self) -> None:
        """Pannello con x invertito e assi scambiati: la calibrazione li riconosce e li salva."""
        from dash.inputs import ABS_X, ABS_Y, TouchCalibration
        from dash.widgets.calibrate import TARGETS
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            app.touch_cal = TouchCalibration({}, {ABS_X: (0, 4095), ABS_Y: (0, 4095)})
            self._tap(app, "calibra")
            self.assertIsNotNone(app.calib)
            for fx, fy in TARGETS:   # controller: raw x segue y dello schermo, raw y segue x al contrario
                raw = (round(250 + fy * 3600), round(3850 - fx * 3500))
                app.handle_tap(Tap(0.5, 0.5, raw), datetime(2026, 9, 24, 7, 42))
            self.assertIsNone(app.calib)
            self.assertEqual(app.notice(), "touch calibrato")
            t = app.touch_cal.map(round(250 + 0.3 * 3600), round(3850 - 0.7 * 3500))
            self.assertAlmostEqual(t.x, 0.7, delta=0.01)
            self.assertAlmostEqual(t.y, 0.3, delta=0.01)
            saved = json.loads((Path(tmp) / "config.local.json").read_text(encoding="utf-8"))
            self.assertTrue(saved["input"]["touch"]["swap_xy"])
            self.assertTrue(saved["input"]["touch"]["invert_x"])
            app.close()

    def test_calibration_rejects_random_taps(self) -> None:
        from dash.widgets.calibrate import solve
        self.assertIsNone(solve([(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)],
                                [(2000, 2000)] * 4))

    def test_power_off_needs_a_second_tap_and_runs_the_command(self) -> None:
        now = datetime(2026, 9, 24, 7, 42)
        calls: list[list[str]] = []

        class Done:
            returncode, stderr = 0, ""

        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            app.cfg["display"]["driver"] = "fb"
            app.run_cmd = lambda cmd, **kw: calls.append(cmd) or Done()
            self._tap(app, "spegni")
            self.assertTrue(app.page.widget.armato())
            self.assertFalse(app.shutting_down)                 # il primo tocco chiede conferma
            self._tap(app, "spegni")
            self.assertTrue(app.shutting_down)
            app.step(now, 0.0, animate=False)                   # prima la schermata, poi il comando
            assert app._power_thread is not None
            app._power_thread.join(5)
            self.assertEqual(calls, [["sudo", "-n", "/usr/bin/systemctl", "poweroff"]])
            app.close()

    def test_power_off_failure_is_shown(self) -> None:
        now = datetime(2026, 9, 24, 7, 42)

        class Denied:
            returncode, stderr = 1, "sudo: a password is required"

        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            app.cfg["display"]["driver"] = "fb"
            app.run_cmd = lambda cmd, **kw: Denied()
            app.power_off()
            app.step(now, 0.0, animate=False)
            thread = app._power_thread
            assert thread is not None
            thread.join(5)
            self.assertFalse(app.shutting_down)
            self.assertIn("non consentito", app.notice())
            app.close()

    def test_power_off_is_simulated_off_the_pi(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            app.run_cmd = lambda *a, **kw: self.fail("nessun comando nel simulatore")
            app.power_off()
            self.assertFalse(app.shutting_down)
            self.assertIn("simulato", app.notice())
            app.close()

    def test_power_monitor_reads_hwmon_and_counts_dips(self) -> None:
        from dash.power import SLOTS, PowerMonitor
        now = datetime(2026, 9, 24, 7, 42)
        with tempfile.TemporaryDirectory() as tmp:
            dev = Path(tmp) / "hwmon1"
            dev.mkdir()
            (dev / "name").write_text("rpi_volt\n")
            alarm = dev / "in0_lcrit_alarm"
            alarm.write_text("0\n")
            mon = PowerMonitor({"sample_s": 5}, hwmon_root=Path(tmp))
            self.assertEqual(mon.source, "hwmon")
            mon.sample(now, 0.0)
            self.assertEqual((mon.under, list(mon.history)[-1]), (False, 0))
            alarm.write_text("1\n")
            mon.sample(now, 2.0)                                 # prima di sample_s: niente
            self.assertFalse(mon.under)
            mon.sample(now, 5.0)
            mon.sample(now, 10.0)                                # stesso calo: uno solo
            self.assertEqual((mon.under, mon.events, list(mon.history)[-1]), (True, 1, 1))
            alarm.write_text("0\n")
            mon.sample(now, 65.0)                                # minuto nuovo, di nuovo ok
            self.assertEqual(list(mon.history)[-2:], [1, 0])
            self.assertEqual(len(mon.history), SLOTS)

    def test_power_monitor_falls_back_to_vcgencmd(self) -> None:
        from unittest import mock
        from dash import power as P

        class Out:
            stdout = "throttled=0x50005\n"               # bit 0: sottotensione adesso

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(P.shutil, "which", return_value="/usr/bin/vcgencmd"):
            mon = P.PowerMonitor({}, hwmon_root=Path(tmp), run=lambda *a, **kw: Out())
            self.assertEqual(mon.source, "vcgencmd")
            self.assertTrue(mon.read())

    def test_low_voltage_is_shown_on_every_page(self) -> None:
        now = datetime(2026, 9, 24, 7, 42)
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            app.page_idx = 0                                      # la home, non le Impostazioni
            ok = app.render(now)
            app.power.record(True, now, 0.0)
            low = app.render(now)
            tab = app.renderer.nav_rows(app)[1]
            area = (tab.x, tab.y, tab.right, tab.bottom)
            pink = app.renderer.c["pink"]
            self.assertFalse(any(px == pink for px in ok.crop(area).getdata()))
            self.assertTrue(any(px == pink for px in low.crop(area).getdata()))
            app.close()

    def test_settings_tab_draws_a_gear(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            img = app.render(datetime(2026, 9, 24, 7, 42))
            tab = app.renderer.nav_rows(app)[1]
            strip = img.crop((tab.right - 30, tab.y, tab.right - 6, tab.bottom))
            cream = app.renderer.c["cream"]
            self.assertGreater(sum(1 for px in strip.getdata() if px == cream), 30)
            app.close()


class TestCli(unittest.TestCase):
    def test_sim_driver_resolves_auto_size(self) -> None:
        """`--driver sim` su una configurazione da Raspberry ('auto'): niente crash."""
        from dash.main import main
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config.json"
            cfg.write_text(json.dumps({"display": {"driver": "fb", "width": "auto",
                                                   "height": "auto"},
                                       "sim": {"out_dir": tmp},
                                       "pages": [{"name": "Home", "widget": "clock"}]}),
                           encoding="utf-8")
            self.assertEqual(main(["-c", str(cfg), "--once", "--demo", "--driver", "sim"]), 0)
            self.assertTrue((Path(tmp) / "frame.png").exists())


class TestNetAndCycles(unittest.TestCase):
    def test_rate_str(self) -> None:
        from dash.widgets.system import rate_str
        self.assertEqual([rate_str(v) for v in (None, 0, 1500, 2_500_000)],
                         ["--", "0 B/s", "2 kB/s", "2.5 MB/s"])

    def test_net_rate_needs_two_samples(self) -> None:
        from dash.sysinfo import Sampler
        s = Sampler()
        self.assertIsNone(s.sample().net_rx)  # primo campione: nessuna differenza disponibile
        st = s.sample()
        if st.net_rx is not None:             # su /proc assente resta None
            self.assertGreaterEqual(st.net_rx, 0.0)
            self.assertEqual(st.net_total, st.net_rx + (st.net_tx or 0))

    def test_cycles_are_fractions(self) -> None:
        from dash.widgets.clock import ClockWidget
        c = ClockWidget.cycles(datetime(2026, 12, 31, 23, 59))
        self.assertAlmostEqual(c["anno"], 1.0, places=2)
        self.assertAlmostEqual(c["mese"], 1.0, places=2)
        capodanno = ClockWidget.cycles(datetime(2026, 1, 1, 0, 0))
        self.assertEqual((capodanno["anno"], capodanno["mese"]), (0.0, 0.0))
        self.assertAlmostEqual(capodanno["settimana"], 3 / 7)  # 1/1/2026 è giovedì


class TestMotion(unittest.TestCase):
    """Motion graphics: tempi puri in motion.py, disegno in render/effects.py."""

    def test_levels_and_config(self) -> None:
        from dash.motion import Motion
        with self.assertRaises(ValueError):
            Motion.from_cfg({"livello": "tanto"})
        off = Motion.from_cfg({"livello": "off"})
        off.start(0.0)
        self.assertIsNone(off.boot_start)             # niente avvio animato
        self.assertIsNone(off.frame_key(1.0))
        self.assertEqual(off.interval(1.0, 0.5), 0.5)  # si torna al ritmo lento
        pieno = Motion.from_cfg({"livello": "pieno", "fps": 8})
        self.assertEqual(pieno.interval(1.0, 0.5), 0.125)
        self.assertEqual(Motion.from_cfg({"fps": 500}).fps, 30.0)  # limite di sicurezza

    def test_config_rejects_bad_motion(self) -> None:
        for bad in ({"livello": "x"}, {"fps": 0}, {"fps": "otto"}):
            cfg = make_cfg(motion={**DEFAULTS["motion"], **bad})
            with self.assertRaises(ConfigError):
                validate(cfg, WIDGET_NAMES)

    def test_easing_and_boot(self) -> None:
        from dash.motion import BOOT_S, Motion, ease_in_out, ease_out, wave
        self.assertEqual((ease_out(0), ease_out(1), ease_in_out(0), ease_in_out(1)), (0, 1, 0, 1))
        self.assertEqual((wave(0, 2), wave(1, 2)), (0.0, 1.0))
        self.assertGreaterEqual(BOOT_S, 5.0)                # avvio lento, la sigla si legge
        m = Motion()
        m.start(10.0)
        self.assertAlmostEqual(m.boot_progress(10.0 + BOOT_S / 2), 0.5)
        self.assertIsNone(m.boot_progress(10.0 + BOOT_S))   # finito: si passa alle pagine
        self.assertIsNone(m.boot_start)

    def test_scramble_keeps_unchanged_digits_and_settles(self) -> None:
        from dash.motion import scramble
        self.assertEqual(scramble("07:43", 1.0, 1), "07:43")       # a fine corsa: testo finale
        for seed in range(20):
            s = scramble("07:43", 0.0, seed, keep="07:42")
            self.assertEqual(s[:4], "07:4")                          # si muove solo l'ultima
        self.assertEqual(scramble("--:--", 0.0, 3), "--:--")         # niente cifre, niente effetto

    def test_live_numbers_decode_only_when_the_page_opens(self) -> None:
        from dash.motion import Motion, Slot
        m = Motion()
        s1 = Slot("system.cpu", "12%", (0, 0), "ls", None, "ink", "orange", (0, 0, 1, 1), True)
        m.slots_drawn([s1], 0.0)
        self.assertEqual(len(m.decodes), 1)                         # prima comparsa: sì
        m.decodes.clear()
        m.slots_drawn([Slot("system.cpu", "13%", (0, 0), "ls", None, "ink", "orange",
                            (0, 0, 1, 1), True)], 1.0)
        self.assertEqual(m.decodes, [])                             # cambia spesso: no

    def _app(self, livello: str = "pieno") -> App:
        cfg = make_cfg(motion={"livello": livello, "fps": 8, "avvio": True})
        return App(cfg, MemDisplay(480, 320), queue.Queue())

    def test_off_level_shows_the_plain_page(self) -> None:
        app = self._app("off")
        now = datetime(2026, 9, 24, 7, 42)
        shown = app.step(now, 0.0)
        self.assertIsNotNone(shown)
        self.assertIsNone(app.step(now, 0.3))                       # niente cambia: niente disegno
        app.close()

    def test_boot_then_first_page_and_tap_skips(self) -> None:
        from dash.motion import BOOT_S
        app = self._app()
        now = datetime(2026, 9, 24, 7, 42)
        app.motion.start(0.0)
        boot = app.step(now, 0.5)
        self.assertIsNotNone(boot)
        self.assertEqual(boot.getpixel((5, 5)), app.renderer.c["bg"])  # niente linguette
        page = app.step(now, BOOT_S + 5)                            # dopo avvio e scansione
        self.assertNotEqual(ImageChops.difference(boot, page).getbbox(), None)
        app2 = self._app()
        app2.motion.start(0.0)
        app2.handle_tap(Tap(0.5, 0.5), now)
        self.assertIsNone(app2.motion.boot_start)                   # il tocco salta l'avvio
        self.assertEqual(app2.page_idx, 0)                          # e non fa altro
        app.close()
        app2.close()

    def test_page_change_wipes_from_the_top(self) -> None:
        from dash.motion import WIPE_S
        app = self._app("eventi")
        now = datetime(2026, 9, 24, 7, 42)
        old = app.step(now, 0.0)
        app.page_idx = 1
        mid = app.step(now, 0.01)
        new_full = app.renderer.render(app, now)
        self.assertIsNotNone(app.motion.wipe_from)
        h = mid.height
        self.assertEqual(mid.crop((0, h - 20, 480, h)).tobytes(),
                         old.crop((0, h - 20, 480, h)).tobytes())  # sotto: ancora la vecchia
        end = app.step(now, WIPE_S + 1.0)                          # decodifiche comprese
        self.assertIsNone(ImageChops.difference(end, new_full).getbbox())
        app.close()

    def test_ambient_effects_stay_inside_their_boxes(self) -> None:
        app = self._app()
        now = datetime(2026, 9, 24, 7, 42)
        app.step(now, 0.0)
        base = app.renderer.render(app, now)
        app.motion.decodes.clear()
        frame = app.renderer.compose(base, app, app.motion, 10.6)   # due punti spenti
        diff = ImageChops.difference(base, frame).getbbox()
        self.assertIsNotNone(diff)
        pad = 60  # aloni e contorni escono un poco dal riquadro registrato
        xs = [b for e in app.renderer.fx for b in (e.box[0] - pad, e.box[2] + pad)]
        ys = [b for e in app.renderer.fx for b in (e.box[1] - pad, e.box[3] + pad)]
        self.assertTrue(min(xs) <= diff[0] and diff[2] <= max(xs))
        self.assertTrue(min(ys) <= diff[1] and diff[3] <= max(ys))
        app.close()

    def test_text_cache_returns_the_same_mask(self) -> None:
        from dash.render import font, text_mask
        f = font("mono", 12)
        self.assertIs(text_mask("meteo", f, "la")[0], text_mask("meteo", f, "la")[0])

    def test_animation_gif(self) -> None:
        from dash.preview import ANIM_SCRIPT, save_animation
        with tempfile.TemporaryDirectory() as tmp:
            path = save_animation(make_cfg(), Path(tmp) / "a.gif", fps=4)
            with Image.open(path) as gif:
                self.assertEqual(gif.size, (480, 320))
                total = 0
                for i in range(gif.n_frames):  # Pillow unisce i fotogrammi uguali consecutivi
                    gif.seek(i)
                    total += gif.info["duration"]
            self.assertEqual(total, sum(round(s * 4) for s, _ in ANIM_SCRIPT) * 250)


class TestLocalConfig(unittest.TestCase):
    def test_local_file_overrides_main(self) -> None:
        from dash.config import load_config
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp) / "config.json"
            main.write_text(json.dumps({"location": {"name": "Ventotene", "lat": 40.796}}),
                            encoding="utf-8")
            cfg = load_config(main, WIDGET_NAMES)
            self.assertEqual(cfg["location"]["name"], "Ventotene")
            (Path(tmp) / "config.local.json").write_text(
                json.dumps({"location": {"name": "Gaeta"}}), encoding="utf-8")
            cfg = load_config(main, WIDGET_NAMES)
            self.assertEqual(cfg["location"]["name"], "Gaeta")
            self.assertEqual(cfg["location"]["lat"], 40.796)  # le altre voci restano

    def test_invalid_local_file_is_reported(self) -> None:
        from dash.config import load_config
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp) / "config.json"
            main.write_text("{}", encoding="utf-8")
            (Path(tmp) / "config.local.json").write_text("{sbagliato", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(main, WIDGET_NAMES)


class TestScreenshots(unittest.TestCase):
    def test_one_png_per_page_offline(self) -> None:
        from dash.preview import save_screenshots
        cfg = make_cfg(display={"width": "auto", "height": "auto"}, location={"mode": "ip"})
        with tempfile.TemporaryDirectory() as tmp:
            paths = save_screenshots(cfg, Path(tmp))
            self.assertEqual([p.name for p in paths], ["01-home.png", "02-meteo.png",
                             "03-timer.png", "04-sveglia.png", "05-sistema.png",
                             "06-needle.png", "07-new.png"])
            for p in paths:
                with Image.open(p) as img:
                    self.assertEqual(img.size, (480, 320))
        self.assertEqual(cfg["location"]["mode"], "fixed")  # nessuna richiesta di rete

    def test_system_screens_offline(self) -> None:
        from dash.preview import save_system_screens
        with tempfile.TemporaryDirectory() as tmp:
            paths = save_system_screens(make_cfg(display={"width": "auto", "height": "auto"}),
                                        Path(tmp))
            self.assertEqual([p.name for p in paths], ["avvio.png", "needle-qr.png",
                             "spegni-conferma.png", "tensione-bassa.png", "calibrazione.png",
                             "spegnimento.png"])
            for p in paths:
                with Image.open(p) as img:
                    self.assertEqual(img.size, (480, 320))


if __name__ == "__main__":
    unittest.main()
