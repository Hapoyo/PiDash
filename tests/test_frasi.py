"""Interprete delle frasi di Needle, azioni personalizzate e nuove azioni: python -m unittest -v"""
from __future__ import annotations

import json
import queue
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any

from dash import azioni, frasi
from dash.app import App
from dash.config import ConfigError, validate
from dash.hue import COLORI, TEMPERATURE, Hue, HueError
from dash.widgets import WIDGET_NAMES
from dash.widgets.alarm import AlarmWidget
from dash.widgets.needle import NeedleWidget
from dash.widgets.timer import TimerState, TimerWidget
from tests.test_dash import BridgeFinto, FakeClock, MemDisplay, make_cfg

STANZE = ["Soggiorno", "Corridoio", "Corridoio Gaeta", "Terrazza", "Tenda"]


def stanze() -> list[str]:
    return STANZE


def chiama(frase: str, voci: list[dict[str, Any]] | None = None) -> Any:
    return frasi.interpreta(frase, voci, stanze)


class TestNumeriEDurate(unittest.TestCase):
    def test_numbers_in_words(self) -> None:
        for testo, atteso in (("zero", 0), ("un", 1), ("dodici", 12), ("venti", 20),
                              ("ventuno", 21), ("ventotto", 28), ("venticinque", 25),
                              ("trentatre", 33), ("novantanove", 99), ("cento", 100),
                              ("centoventi", 120), ("duecento", 200), ("45", 45)):
            self.assertEqual(frasi.numero(testo), atteso, testo)
        for no in ("casa", "ventiquindici", "centro", ""):
            self.assertIsNone(frasi.numero(no), no)

    def test_durations_in_every_form(self) -> None:
        casi = {
            "timer 5 minuti": 300, "timer cinque minuti": 300, "timer di 90 secondi": 90,
            "timer 1h 15min": 4500, "timer un'ora": 3600, "timer 2 ore": 7200,
            "timer un'ora e mezza": 5400, "timer 1 ora e 30": 5400, "timer 2 ore e un quarto": 8100,
            "timer mezz'ora": 1800, "timer mezza ora": 1800, "timer un quarto d'ora": 900,
            "timer tre quarti d'ora": 2700, "timer due minuti e mezzo": 150,
            "timer un minuto e 30 secondi": 90, "timer 5 minuti e 30 secondi": 330,
            "timer venticinque minuti": 1500, "timer 5": 300, "timer di dieci": 600,
            "avvisami tra dieci minuti": 600, "ricordami tra 3 minuti": 180,
            "partenza regata timer 5 minuti": 300,
        }
        for frase, secondi in casi.items():
            self.assertEqual(chiama(frase), [("start_timer", {"seconds": secondi})], frase)

    def test_timer_control_words(self) -> None:
        self.assertEqual(chiama("ferma il timer"), [("stop_timer", {})])
        self.assertEqual(chiama("annulla il timer"), [("stop_timer", {})])
        self.assertEqual(chiama("metti in pausa il timer"), [("pause_timer", {})])
        self.assertEqual(chiama("riprendi il timer"), [("resume_timer", {})])
        self.assertIsNone(chiama("timer"))                    # senza durata non si indovina

    def test_alarm_times_in_every_form(self) -> None:
        casi = {
            "svegliami alle 7": "07:00", "sveglia alle 7:30": "07:30", "sveglia alle 7.45": "07:45",
            "sveglia alle sette": "07:00", "svegliami alle 7 e mezza": "07:30",
            "sveglia alle sette e un quarto": "07:15", "sveglia alle 7 e tre quarti": "07:45",
            "sveglia alle 7 e 15": "07:15", "sveglia alle 8 meno un quarto": "07:45",
            "sveglia alle 8 meno 10": "07:50", "sveglia all'una": "01:00",
            "sveglia alle 9 di sera": "21:00", "sveglia alle 3 del pomeriggio": "15:00",
            "sveglia alle 11 di notte": "23:00", "sveglia alle 3 di notte": "03:00",
            "sveglia a mezzogiorno": "12:00", "sveglia a mezzanotte": "00:00",
            "mettimi la sveglia alle 6:45": "06:45",
        }
        for frase, ora in casi.items():
            self.assertEqual(chiama(frase), [("set_alarm", {"time": ora})], frase)

    def test_alarm_days(self) -> None:
        casi = {
            "sveglia alle 7 dal lunedì al venerdì": [0, 1, 2, 3, 4],
            "sveglia alle 7 nei giorni feriali": [0, 1, 2, 3, 4],
            "sveglia alle 7 nel weekend": [5, 6], "sveglia alle 7 sabato e domenica": [5, 6],
            "sveglia alle 7 il lunedì e il giovedì": [0, 3],
            "sveglia alle 7 dal venerdì al lunedì": [0, 4, 5, 6],     # la settimana ricomincia
            "sveglia alle 7 ogni sabato": [5],
        }
        for frase, giorni in casi.items():
            self.assertEqual(chiama(frase), [("set_alarm", {"time": "07:00", "days": giorni})], frase)
        for tutti in ("sveglia alle 7 tutti i giorni", "sveglia alle 7 ogni giorno", "sveglia alle 7"):
            self.assertEqual(chiama(tutti), [("set_alarm", {"time": "07:00"})], tutti)

    def test_deleting_alarms_is_never_by_mistake(self) -> None:
        self.assertEqual(chiama("cancella la sveglia delle 7"),
                         [("delete_alarm", {"time": "07:00"})])
        self.assertEqual(chiama("cancella tutte le sveglie"), [("delete_alarm", {})])
        self.assertIsNone(chiama("cancella la sveglia"))        # quale? non si cancella tutto
        self.assertIsNone(chiama("spegni la sveglia"))          # non è una luce: va al modello

    def test_lights_requests(self) -> None:
        casi = {
            "accendi la luce del soggiorno": {"room": "Soggiorno", "on": True},
            "spegni tutte le luci": {"room": "tutte", "on": False},
            "luce soggiorno al 50": {"room": "Soggiorno", "percent": 50},
            "soggiorno al cinquanta per cento": {"room": "Soggiorno", "percent": 50},
            "accendi il corridoio gaeta al massimo": {"room": "Corridoio Gaeta", "on": True,
                                                       "percent": 100},
            "accendi il corridoio": {"room": "Corridoio", "on": True},      # non "corridoio gaeta"
            "luce del soggiorno a metà": {"room": "Soggiorno", "percent": 50},
            "metti la luce del soggiorno rossa": {"room": "Soggiorno", "color": "rosso"},
            "luce azzurra in terrazza": {"room": "Terrazza", "color": "azzurro"},
            "luce calda in terrazza": {"room": "Terrazza", "temp": "calda"},
            "luce fredda nel soggiorno": {"room": "Soggiorno", "temp": "fredda"},
            "alza la luce del corridoio": {"room": "Corridoio", "delta": 20},
            "abbassa la luce del soggiorno": {"room": "Soggiorno", "delta": -20},
            "abbassa la luce del soggiorno di 30 percento": {"room": "Soggiorno", "delta": -30},
            "alza la luce della tenda del 10%": {"room": "Tenda", "delta": 10},
            "accendi la luce in cucina": {"room": "cucina", "on": True},   # lo dirà l'azione
            "accendi la luce": {"room": "", "on": True},
        }
        for frase, args in casi.items():
            self.assertEqual(chiama(frase), [("lights", args)], frase)

    def test_off_clears_every_other_effect(self) -> None:
        self.assertEqual(chiama("spegni la luce rossa del soggiorno al 50"),
                         [("lights", {"room": "Soggiorno", "on": False})])

    def test_what_is_not_understood_goes_to_the_model(self) -> None:
        for frase in ("che tempo fa a roma", "apri il meteo", "alza il volume", "",
                      "non accendere la luce", "accendi e spegni il soggiorno", "timer"):
            self.assertIsNone(chiama(frase), frase)

    def test_without_a_bridge_the_text_is_kept_for_the_error(self) -> None:
        self.assertEqual(frasi.interpreta("accendi la luce del soppalco", None, None),
                         [("lights", {"room": "soppalco", "on": True})])


class TestAzioniPersonalizzate(unittest.TestCase):
    VOCI = [
        {"nome": "pasta", "frasi": ["pasta", "spaghetti"], "timer": {"minuti": 9}},
        {"nome": "buonanotte", "frasi": ["buonanotte", "vado a dormire"], "sveglia": "07:00",
         "giorni": [0, 1, 2, 3, 4],
         "luci": [{"stanza": "tutte", "acceso": False}], "pagina": "alarm"},
        {"nome": "cinema", "frasi": ["cinema"],
         "luci": [{"stanza": "soggiorno", "percentuale": 15, "temperatura": "calda"},
                  {"stanza": "corridoio", "acceso": False}]},
        {"nome": "cinema grande", "frasi": ["cinema grande"], "luci": [{"stanza": "tutte", "acceso": False}]},
    ]

    def test_phrase_keys_become_calls(self) -> None:
        self.assertEqual(chiama("metti il timer della pasta", self.VOCI),
                         [("start_timer", {"seconds": 540})])
        self.assertEqual(chiama("SPAGHETTI!", self.VOCI), [("start_timer", {"seconds": 540})])
        self.assertEqual(chiama("vado a dormire", self.VOCI), [
            ("start_timer", {"seconds": 540})][:0] + [
            ("set_alarm", {"time": "07:00", "days": [0, 1, 2, 3, 4]}),
            ("lights", {"room": "tutte", "on": False}), ("open_alarm", {})])
        self.assertEqual(chiama("modalità cinema", self.VOCI), [
            ("lights", {"room": "soggiorno", "percent": 15, "temp": "calda"}),
            ("lights", {"room": "corridoio", "on": False})])

    def test_the_longest_key_wins(self) -> None:
        self.assertEqual(chiama("cinema grande", self.VOCI), [("lights", {"room": "tutte", "on": False})])

    def test_custom_actions_come_before_the_rules(self) -> None:
        voci = [{"nome": "x", "frasi": ["timer pasta"], "timer": {"secondi": 30}}]
        self.assertEqual(chiama("timer pasta 5 minuti", voci), [("start_timer", {"seconds": 30})])

    def test_config_validation(self) -> None:
        validate(make_cfg(needle={"azioni": self.VOCI}), WIDGET_NAMES)
        validi = {"nome": "a", "frasi": ["a"], "timer": {"minuti": 1}}
        for guasto in ({"nome": ""}, {"frasi": []}, {"frasi": [""]}, {"frasi": "a"},
                       {"timer": {"minuti": 0}}, {"timer": {"giorni": 1}}, {"timer": {"ore": 4}},
                       {"timer": {"minuti": True}}, {"sveglia": "25:00"}, {"sveglia": 7},
                       {"giorni": [0]}, {"sveglia": "07:00", "giorni": [7]},
                       {"sveglia": "07:00", "giorni": []}, {"pagina": "ovunque"},
                       {"luci": []}, {"luci": [{"acceso": True}]},
                       {"luci": [{"stanza": "x", "percentuale": 101}]},
                       {"luci": [{"stanza": "x", "colore": "marrone"}]},
                       {"luci": [{"stanza": "x", "temperatura": "tiepida"}]},
                       {"luci": [{"stanza": "x", "colore": "rosso", "temperatura": "calda"}]},
                       {"luci": [{"stanza": "x", "acceso": "si"}]}):
            voce = {**validi, **guasto}
            if "timer" in guasto and guasto["timer"] == {"minuti": 0}:
                voce = {"nome": "a", "frasi": ["a"], "timer": {"minuti": 0}}
            with self.assertRaises(ConfigError, msg=str(guasto)):
                validate(make_cfg(needle={"azioni": [voce]}), WIDGET_NAMES)
        with self.assertRaises(ConfigError):
            validate(make_cfg(needle={"azioni": [{"nome": "a", "frasi": ["a"]}]}), WIDGET_NAMES)  # fa nulla
        with self.assertRaises(ConfigError):
            validate(make_cfg(needle={"azioni": [validi] * 31}), WIDGET_NAMES)
        with self.assertRaises(ConfigError):
            validate(make_cfg(needle={"regole": "si"}), WIDGET_NAMES)

    def test_openable_pages_match_the_actions(self) -> None:
        from dash.config import PAGINE_APRIBILI
        self.assertEqual(set(PAGINE_APRIBILI), set(azioni.PAGINE))


class TestNuoveAzioni(unittest.TestCase):
    NOW = datetime(2026, 9, 24, 7, 42)

    def _app(self, tmp: str, **needle: Any) -> tuple[App, BridgeFinto]:
        main = Path(tmp) / "config.json"
        main.write_text("{}", encoding="utf-8")
        cfg = make_cfg(pages=[{"name": "Home", "widget": "clock"}, {"name": "+", "widget": "new"}],
                       needle=needle)
        app = App(cfg, MemDisplay(480, 320), queue.Queue(), config_path=main)
        bridge = BridgeFinto()
        app.hue = Hue({"bridge": "192.168.1.73", "key": "SEGRETO"}, send=bridge, clock=FakeClock())
        return app, bridge

    def test_hue_body_for_colour_temperature_and_relative_brightness(self) -> None:
        hue = Hue({"bridge": "x", "key": "y"}, send=(b := BridgeFinto()), clock=FakeClock())
        stanza = hue.trova("soggiorno")
        hue.imposta(stanza, True, None, "rosso")
        hue.imposta(stanza, True, 30, None, "calda")
        hue.imposta(stanza, True, None, None, None, 20)
        hue.imposta(stanza, True, None, None, None, -100)
        hue.imposta(stanza, True, 50, "blu", None, 20)      # il livello esatto vince sulla variazione
        self.assertEqual([c[2] for c in b.put()], [
            {"on": True, "hue": COLORI["rosso"][0], "sat": COLORI["rosso"][1]},
            {"on": True, "bri": 76, "ct": TEMPERATURE["calda"]},
            {"on": True, "bri_inc": 51}, {"on": True, "bri_inc": -254},
            {"on": True, "bri": 127, "hue": COLORI["blu"][0], "sat": COLORI["blu"][1]}])

    def test_lights_action_sets_what_was_asked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app, b = self._app(tmp)
            r = azioni.esegui(app, "lights", {"room": "Soggiorno", "color": "rosso", "percent": 40})
            self.assertEqual(r, "luci Soggiorno accese al 40% rosso (non raggiungibili)")
            self.assertEqual(b.put()[-1][2]["on"], True)                    # il colore accende
            r = azioni.esegui(app, "lights", {"room": "tutte", "on": False, "percent": 40})
            self.assertEqual((r, b.put()[-1]), ("tutte le luci spente",
                                                ("PUT", "groups/0/action", {"on": False})))
            azioni.esegui(app, "lights", {"room": "Tenda", "delta": -20})
            self.assertEqual(b.put()[-1][2], {"on": True, "bri_inc": -51})
            app.close()

    def test_lights_action_refuses_what_it_cannot_do(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app, b = self._app(tmp)
            for args, errore in (
                    ({"room": ""}, "errore: di quale stanza?"),
                    ({"room": "tutte", "color": "marrone"}, "errore: colore sconosciuto: marrone"),
                    ({"room": "tutte", "temp": "tiepida"}, "errore: temperatura sconosciuta: tiepida"),
                    ({"room": "tutte", "percent": 0}, "errore: luminosità da 1 a 100"),
                    ({"room": "tutte", "percent": "molto"}, "errore: luminosità non valida"),
                    ({"room": "tutte", "delta": 101}, "errore: variazione da −100 a 100"),
                    ({"room": "cucina", "on": True}, "errore: stanza sconosciuta: cucina")):
                self.assertEqual(azioni.esegui(app, "lights", args), errore, args)
            self.assertEqual(b.put(), [])                    # niente è arrivato al bridge
            app.close()

    def test_alarm_with_days_and_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app, _ = self._app(tmp)
            self.assertEqual(azioni.esegui(app, "set_alarm", {"time": "06:45", "days": [0, 1, 2, 3, 4]}),
                             "sveglia 06:45 lun-ven")
            self.assertEqual(azioni.esegui(app, "set_alarm", {"time": "09:00"}),
                             "sveglia 09:00 ogni giorno")
            pagina = app.find_page("alarm")
            assert pagina is not None and isinstance(pagina.widget, AlarmWidget)
            self.assertEqual(len(pagina.widget.alarms), 2)
            saved = json.loads((Path(tmp) / "config.local.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["alarm"]["alarms"][0]["days"], [0, 1, 2, 3, 4])
            for giorni in ([], [7], ["x"], 5):
                self.assertEqual(azioni.esegui(app, "set_alarm", {"time": "07:00", "days": giorni}),
                                 "errore: giorni non validi")
            self.assertEqual(azioni.esegui(app, "delete_alarm", {"time": "06:45"}), "sveglia 06:45 tolta")
            self.assertEqual(azioni.esegui(app, "delete_alarm", {"time": "06:45"}),
                             "errore: nessuna sveglia alle 06:45")
            self.assertEqual(azioni.esegui(app, "delete_alarm", {}), "sveglia tolta")
            self.assertEqual(azioni.esegui(app, "delete_alarm", {}), "errore: nessuna sveglia")
            self.assertEqual(pagina.widget.alarms, [])
            saved = json.loads((Path(tmp) / "config.local.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["alarm"]["alarms"], [])
            app.close()

    def test_deleting_the_ringing_alarm_silences_it(self) -> None:
        w = AlarmWidget({"alarms": [{"time": "07:42", "days": list(range(7))}]})
        w.update(self.NOW)
        self.assertIsNotNone(w.ringing)
        self.assertEqual(w.remove_alarms(7, 42), 1)
        self.assertIsNone(w.ringing)

    def test_timer_stop_pause_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app, _ = self._app(tmp)
            self.assertEqual(azioni.esegui(app, "stop_timer", {}), "errore: nessun timer")
            self.assertEqual(azioni.esegui(app, "start_timer", {"seconds": 150}), "timer 2'30\" avviato")
            pagina = app.find_page("timer")
            assert pagina is not None and isinstance(pagina.widget, TimerWidget)
            t = pagina.widget
            self.assertEqual(azioni.esegui(app, "resume_timer", {}), "errore: il timer non è in pausa")
            self.assertEqual(azioni.esegui(app, "pause_timer", {}), "timer in pausa")
            self.assertIs(t.state, TimerState.PAUSED)
            self.assertEqual(azioni.esegui(app, "pause_timer", {}), "errore: il timer non sta scorrendo")
            self.assertEqual(azioni.esegui(app, "resume_timer", {}), "timer riparte")
            self.assertIs(t.state, TimerState.RUNNING)
            self.assertEqual(azioni.esegui(app, "stop_timer", {}), "timer fermato")
            self.assertEqual((t.state, t.remaining()), (TimerState.IDLE, 150.0))
            self.assertEqual(azioni.esegui(app, "stop_timer", {}), "errore: timer già fermo")
            self.assertEqual(azioni.esegui(app, "start_timer", {"seconds": 0}), "errore: timer da 1 s a 180'")
            app.close()

    def test_every_rule_call_is_executable(self) -> None:
        """Ciò che l'interprete e le azioni personalizzate producono esiste tra le azioni."""
        for frase in ("timer 5 minuti", "ferma il timer", "metti in pausa il timer", "riprendi il timer",
                      "sveglia alle 7", "cancella le sveglie", "accendi il soggiorno"):
            for nome, _ in chiama(frase):
                self.assertIn(nome, azioni.AZIONI, nome)
        for nome in azioni.SOLO_REGOLE:
            self.assertIn(nome, azioni.AZIONI)
        self.assertEqual({azioni.categoria(n) for n in ("lights", "lights_on")}, {"luci"})


class TestNeedleConRegole(unittest.TestCase):
    """La frase arriva al widget: l'interprete risponde da solo, il modello solo se serve."""

    NOW = datetime(2026, 9, 24, 7, 42)

    def _app(self, tmp: str, modello: Any, **needle: Any) -> tuple[App, NeedleWidget, BridgeFinto]:
        main = Path(tmp) / "config.json"
        main.write_text("{}", encoding="utf-8")
        needle.setdefault("queries", ["timer 5 minuti", "accendi il soggiorno", "che tempo fa a roma"])
        cfg = make_cfg(pages=[{"name": "Home", "widget": "clock"},
                              {"name": "Needle", "widget": "needle"},
                              {"name": "Meteo", "widget": "weather"}, {"name": "+", "widget": "new"}],
                       needle=needle)
        app = App(cfg, MemDisplay(480, 320), queue.Queue(), config_path=main)
        app.page_idx = 1
        w = app.page.widget
        assert isinstance(w, NeedleWidget)
        w.load_demo()
        w._post = modello
        bridge = BridgeFinto()
        app.hue = Hue({"bridge": "192.168.1.73", "key": "SEGRETO"}, send=bridge, clock=FakeClock())
        return app, w, bridge

    @staticmethod
    def _attendi(w: NeedleWidget) -> None:
        from tests.test_dash import TestNeedle
        TestNeedle._wait(w)

    def test_rules_answer_without_calling_the_model(self) -> None:
        def mai(*a: Any) -> Any:
            raise AssertionError("il modello non doveva essere interrogato")

        with tempfile.TemporaryDirectory() as tmp:
            app, w, bridge = self._app(tmp, mai)
            w.ask(0)
            self._attendi(w)
            app.step(self.NOW, 0.0, animate=False)
            pagina = app.find_page("timer")
            assert pagina is not None and isinstance(pagina.widget, TimerWidget)
            self.assertEqual(pagina.widget.shown_remaining(), 300)
            r = w.snapshot()[2]
            self.assertEqual((r.chiamate, r.confidenza), (("start_timer(seconds=300)",), 1.0))
            self.assertEqual(r.esito, "timer 5' avviato")
            self.assertEqual(w.umore(), "fatto")
            app.close()

    def test_rules_find_the_room_through_the_bridge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app, w, bridge = self._app(tmp, lambda *a: {})
            w.ask(1)
            self._attendi(w)
            app.step(self.NOW, 0.0, animate=False)
            self.assertEqual(bridge.put(), [("PUT", "groups/2/action", {"on": True})])
            app.close()

    def test_phrases_without_a_rule_still_go_to_the_model(self) -> None:
        def modello(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
            return {} if url.endswith("/reset") else {
                "success": True, "confidence": 0.95,
                "function_calls": [{"name": "open_weather", "arguments": {}}]}

        with tempfile.TemporaryDirectory() as tmp:
            app, w, _ = self._app(tmp, modello)
            w.ask(2)
            self._attendi(w)
            app.step(self.NOW, 0.0, animate=False)
            self.assertEqual(app.page.kind, "weather")
            self.assertEqual(w.snapshot()[2].chiamate, ("open_weather()",))
            app.close()

    def test_rules_can_be_turned_off(self) -> None:
        calls: list[str] = []

        def modello(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
            calls.append(url)
            return {"success": True, "confidence": 0.95, "function_calls": []}

        with tempfile.TemporaryDirectory() as tmp:
            app, w, _ = self._app(tmp, modello, regole=False)
            w.ask(0)
            self._attendi(w)
            self.assertTrue(any(u.endswith("/complete") for u in calls))
            app.close()

    def test_rules_work_while_the_service_is_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app, w, _ = self._app(tmp, lambda *a: {})
            w._online = False
            w.ask(0)                                  # "timer 5 minuti": non serve il modello
            self._attendi(w)
            app.step(self.NOW, 0.0, animate=False)
            self.assertIsNotNone(app.find_page("timer"))
            w._last = None
            w.ask(2)                                  # "che tempo fa a roma": serve il modello, che è spento
            self._attendi(w)
            self.assertIsNone(w.snapshot()[2])
            app.close()

    def test_custom_action_runs_every_step(self) -> None:
        voci = [{"nome": "buonanotte", "frasi": ["buonanotte"], "sveglia": "07:00", "giorni": [0, 1, 2, 3, 4],
                 "luci": [{"stanza": "tutte", "acceso": False}], "timer": {"minuti": 20}}]
        with tempfile.TemporaryDirectory() as tmp:
            app, w, bridge = self._app(tmp, lambda *a: {}, azioni=voci, queries=["buonanotte"])
            w.ask(0)
            self._attendi(w)
            app.step(self.NOW, 0.0, animate=False)
            timer, sveglia = app.find_page("timer"), app.find_page("alarm")
            assert timer is not None and sveglia is not None
            self.assertEqual(timer.widget.shown_remaining(), 1200)                # type: ignore[attr-defined]
            self.assertEqual(sveglia.widget.alarms[0].days, frozenset(range(5)))  # type: ignore[attr-defined]
            self.assertEqual(bridge.put(), [("PUT", "groups/0/action", {"on": False})])
            app.close()

    def test_hue_down_is_reported_not_swallowed(self) -> None:
        def morto(metodo: str, percorso: str, corpo: Any) -> Any:
            raise HueError("bridge non risponde")

        with tempfile.TemporaryDirectory() as tmp:
            app, w, _ = self._app(tmp, lambda *a: {})
            app.hue = Hue({"bridge": "x", "key": "y"}, send=morto)
            w.ask(1)                                  # "accendi il soggiorno" con il bridge muto
            self._attendi(w)
            app.step(self.NOW, 0.0, animate=False)
            self.assertEqual(w.snapshot()[2].esito, "errore: bridge non risponde")
            self.assertEqual(w.umore(), "errore")
            app.close()


class TestUmore(unittest.TestCase):
    def _widget(self) -> tuple[NeedleWidget, FakeClock]:
        clock = FakeClock()
        w = NeedleWidget({"queries": ["a"]}, clock=clock)
        return w, clock

    def test_moods_follow_the_service_and_the_last_answer(self) -> None:
        from dataclasses import replace

        from dash.widgets.needle import RECENTE_S, Risposta
        w, clock = self._widget()
        self.assertEqual(w.umore(), "controllo")
        w._online = False
        self.assertEqual(w.umore(), "offline")
        w._online = True
        self.assertEqual(w.umore(), "pronto")
        w._busy = True
        self.assertEqual(w.umore(), "penso")
        w._busy = False
        w._last = Risposta("a", ("open_home()",), 0.9, 10, t=clock())
        self.assertEqual(w.umore(), "fatto")
        w._last = replace(w._last, esito="errore: bridge non risponde")
        self.assertEqual(w.umore(), "errore")
        w._last = replace(w._last, esito="confidenza bassa: non eseguo")
        self.assertEqual(w.umore(), "dubbio")
        w._last = Risposta("a", (), None, 10, t=clock())
        self.assertEqual(w.umore(), "dubbio")                 # nessuna funzione riconosciuta
        w._last = Risposta("a", (), None, 10, errore="servizio non risponde", t=clock())
        self.assertEqual(w.umore(), "errore")
        clock.t += RECENTE_S
        self.assertEqual(w.umore(), "pronto")                 # la faccia dell'esito passa
        w.umore_forzato = "penso"
        self.assertEqual(w.umore(), "penso")

    def test_mood_is_part_of_the_state_key(self) -> None:
        """Quando la faccia cambia la pagina base si ridisegna."""
        from dash.widgets.needle import RECENTE_S, Risposta
        w, clock = self._widget()
        w._online = True
        w._last = Risposta("a", ("open_home()",), 0.9, 10, t=clock())
        prima = w.state_key(datetime(2026, 9, 24))
        clock.t += RECENTE_S
        self.assertNotEqual(w.state_key(datetime(2026, 9, 24)), prima)


if __name__ == "__main__":
    unittest.main()
