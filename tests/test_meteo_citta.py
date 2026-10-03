"""Meteo di un'altra città dalla pagina "premi e parla": python -m unittest -v"""
from __future__ import annotations

import queue
import shutil
import tempfile
import time
import unittest
import urllib.error
from datetime import datetime
from pathlib import Path
from unittest import mock

from dash import azioni, frasi, location
from dash.app import App
from dash.widgets.weather import WeatherWidget
from dash.voce import Frase
from tests import test_dash as td

NOW = datetime(2026, 9, 24, 7, 42)
FORLI = ("Forlì", 44.22, 12.04)


def chiama(frase: str) -> object:
    return frasi.interpreta(frase, None, lambda: [])


class TestFrasiMeteo(unittest.TestCase):
    def test_city_in_every_form(self) -> None:
        for frase, citta in (("Meteo Roma", "Roma"), ('meteo "Roma"', "Roma"), ("meteo “New York”", "New York"),
                             ("meteo a Forlì", "Forlì"), ("il meteo di Genova!", "Genova"),
                             ("METEO  'La Spezia'", "La Spezia"), ("meteo per Reggio Emilia", "Reggio Emilia")):
            self.assertEqual(chiama(frase), [("set_weather_city", {"city": citta})], frase)

    def test_back_to_the_dashboard_place(self) -> None:
        for frase in ("meteo qui", "Meteo locale", "meteo di casa", "il meteo qui"):
            self.assertEqual(chiama(frase), [("set_weather_city", {"city": ""})], frase)

    def test_not_a_city_goes_to_the_model(self) -> None:
        for frase in ("meteo", "meteo oggi", "meteo di domani", "meteo " + "a" * 70,
                      "meteo uno due tre quattro cinque sei"):
            self.assertIsNone(chiama(frase), frase)

    def test_other_rules_are_untouched(self) -> None:
        self.assertEqual(chiama("timer 5 minuti"), [("start_timer", {"seconds": 300})])
        self.assertIsNone(chiama("che tempo fa a Roma"))


class TestAzioneMeteo(unittest.TestCase):
    def _app(self) -> App:
        cfg = td.make_cfg()
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        main = Path(tmp) / "config.json"
        main.write_text("{}", encoding="utf-8")
        app = App(cfg, td.MemDisplay(480, 320), queue.Queue(), config_path=main)
        self.addCleanup(app.close)
        return app

    @staticmethod
    def _wx(app: App) -> WeatherWidget:
        w = app.find_page("weather")
        assert w is not None and isinstance(w.widget, WeatherWidget)
        return w.widget

    def test_city_changes_the_weather_not_the_location(self) -> None:
        app = self._app()
        wx = self._wx(app)
        casa = app.widgets["clock"].location.snapshot() if "clock" in app.widgets else wx.location.snapshot()
        with mock.patch.object(azioni, "geocode", return_value=FORLI) as g:
            esito = azioni.esegui(app, "set_weather_city", {"city": "Forlì"})
        g.assert_called_once()
        self.assertEqual(esito, "meteo di forlì")
        self.assertEqual(wx.place(), FORLI)
        self.assertEqual(wx.city(), "Forlì")
        self.assertIn("latitude=44.22", wx.build_url())
        self.assertEqual(wx.location.snapshot(), casa)      # la posizione configurata resta
        self.assertEqual(app.page.kind, "weather")

    def test_city_changes_the_state_key_and_clears_old_data(self) -> None:
        app = self._app()
        wx = self._wx(app)
        wx.demo = False
        wx._data = {"current": {}}
        prima = wx.state_key(NOW)
        wx.set_city(*FORLI)
        self.assertNotEqual(wx.state_key(NOW), prima)
        self.assertIsNone(wx.snapshot())                    # niente dati di un altro luogo
        self.assertTrue(wx._wake.is_set())                  # il thread scarica subito

    def test_here_goes_back(self) -> None:
        app = self._app()
        wx = self._wx(app)
        wx.set_city(*FORLI)
        self.assertEqual(azioni.esegui(app, "set_weather_city", {"city": ""}), "meteo del dashboard")
        self.assertEqual(wx.city(), "")
        self.assertEqual(wx.place(), wx.location.snapshot())

    def test_unknown_city_leaves_the_weather_alone(self) -> None:
        app = self._app()
        wx = self._wx(app)
        dati = wx.snapshot()
        with mock.patch.object(azioni, "geocode", return_value=None):
            esito = azioni.esegui(app, "set_weather_city", {"city": "Xyzzyville"})
        self.assertEqual(esito, "errore: città non trovata: Xyzzyville")
        self.assertEqual((wx.city(), wx.snapshot()), ("", dati))

    def test_network_error_is_reported(self) -> None:
        app = self._app()
        with mock.patch.object(azioni, "geocode", side_effect=urllib.error.URLError("giù")):
            esito = azioni.esegui(app, "set_weather_city", {"city": "Roma"})
        self.assertEqual(esito, "errore: ricerca di Roma non riuscita (rete)")
        self.assertEqual(self._wx(app).city(), "")

    def test_phrase_from_the_phone_end_to_end(self) -> None:
        app = self._app()
        wx = self._wx(app)
        w = app.needle()
        w.load_demo()
        w.demo = False
        w._checked = w._clock()
        app.events.put(Frase(1, 'Meteo "Forlì"'))
        with mock.patch.object(azioni, "geocode", return_value=FORLI):
            app.step(NOW, 0.0, animate=False)
            td.TestNeedle._wait(w)
            for i in range(50):
                app.step(NOW, 0.1 * i, animate=False)
                s = app.voce_stato()
                if s["risposte"] > s["attesa"] and not s["lavora"]:
                    break
                time.sleep(0.01)
        self.assertEqual((s["domanda"], s["esito"]), ('Meteo "Forlì"', "meteo di forlì"))
        self.assertEqual(wx.city(), "Forlì")

    def test_category_and_rules_only(self) -> None:
        self.assertEqual(azioni.categoria("set_weather_city"), "pagina")
        self.assertIn("set_weather_city", azioni.SOLO_REGOLE)


class TestGeocode(unittest.TestCase):
    def test_result_and_missing(self) -> None:
        with mock.patch.object(location, "_get_json", return_value={"results": [
                {"name": "Forlì", "latitude": 44.22, "longitude": 12.04}]}) as g:
            self.assertEqual(location.geocode("Forlì", timeout=3), FORLI)
        self.assertIn("name=For", g.call_args.args[0])
        self.assertEqual(g.call_args.kwargs["timeout"], 3)
        with mock.patch.object(location, "_get_json", return_value={"generationtime_ms": 0.4}):
            self.assertIsNone(location.geocode("Xyzzyville"))
        with mock.patch.object(location, "_get_json", return_value={"results": [{"name": "x"}]}):
            self.assertIsNone(location.geocode("x"))


if __name__ == "__main__":
    unittest.main()
