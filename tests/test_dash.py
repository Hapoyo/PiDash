"""Test di base: python -m unittest -v"""
from __future__ import annotations

import copy
import json
import queue
import tempfile
import unittest
from typing import Any
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageChops

from dash.config import DEFAULTS, ConfigError, _merge, validate
from dash.display.base import Display
from dash.inputs import Event, Tap
from dash.app import App
from dash.widgets import WIDGET_NAMES
from dash.widgets.alarm import AlarmWidget
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

    def test_back_cycles_preset(self) -> None:
        t = TimerWidget({"presets_s": [60, 300]})
        t.on_back(datetime.now())
        self.assertEqual(t.duration, 300)


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
                       timer={"presets_s": [300], "labels": {"300": "partenza"}},
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
            self.assertEqual([v.label for v in plus.voci()], ["timer", "sveglia"])
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

    def test_tap_on_a_chip_selects_it(self) -> None:
        app = App(make_cfg(pages=[{"name": "Home", "widget": "clock"},
                                  {"name": "+", "widget": "new"}]),
                  MemDisplay(480, 320), queue.Queue())
        app.page_idx = 1
        boxes = app.renderer.select_boxes(app)
        self.assertEqual(len(boxes), len(app.pages[-1].widget.voci()))
        b = boxes[1]
        app.handle_tap(Tap((b.x + b.w / 2) / 480, (b.y + b.h / 2) / 320),
                       datetime(2026, 9, 24, 7, 42))
        self.assertEqual(app.pages[-1].widget.idx, 1)
        self.assertEqual(len(app.pages), 2)  # il tocco su una voce non crea nulla
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
                             "03-timer.png", "04-sveglia.png", "05-sistema.png", "06-new.png"])
            for p in paths:
                with Image.open(p) as img:
                    self.assertEqual(img.size, (480, 320))
        self.assertEqual(cfg["location"]["mode"], "fixed")  # nessuna richiesta di rete


if __name__ == "__main__":
    unittest.main()
