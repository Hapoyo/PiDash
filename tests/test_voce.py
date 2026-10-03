"""Pagina "premi e parla": server, frasi in coda, stato per il telefono, certificato."""
from __future__ import annotations

import copy
import hashlib
import http.client
import json
import queue
import shutil
import ssl
import subprocess
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any

from dash import qr
from dash.app import App
from dash.render.pages import needle as needle_page
from dash.config import DEFAULTS, ConfigError, _merge, validate
from dash.layout import Box
from dash.voce import Frase, VoceServer, avvia, certificato, contesto_tls, pulisci
from dash.widgets import WIDGET_NAMES
from dash.widgets.needle import NeedleWidget
from tests import test_dash as td

NOW = datetime(2026, 9, 24, 7, 42)


class TestVoceServer(unittest.TestCase):
    def setUp(self) -> None:
        self.events: queue.Queue[Any] = queue.Queue()
        self.servers: list[VoceServer] = []

    def tearDown(self) -> None:
        for s in self.servers:
            s.close()

    def _server(self, **cfg: Any) -> int:
        s = VoceServer(cfg, self.events, lambda: {"id": 0, "stato": "pronto"})
        self.servers.append(s)
        return s.avvia("127.0.0.1", 0)

    @staticmethod
    def _req(porta: int, metodo: str, path: str, body: Any = None,
             headers: dict[str, str] | None = None) -> tuple[int, bytes]:
        c = http.client.HTTPConnection("127.0.0.1", porta, timeout=5)
        data = json.dumps(body).encode() if body is not None else None
        c.request(metodo, path, body=data, headers=headers or {})
        r = c.getresponse()
        out = r.status, r.read()
        c.close()
        return out

    def test_serves_the_page_and_the_fonts(self) -> None:
        porta = self._server()
        code, body = self._req(porta, "GET", "/")
        self.assertEqual(code, 200)
        self.assertIn("premi<br>e parla", body.decode())
        self.assertIn("it-IT", body.decode())
        self.assertEqual(self._req(porta, "GET", "/fonts/SpaceGrotesk.ttf")[0], 200)
        self.assertEqual(self._req(porta, "GET", "/fonts/../config.json")[0], 404)

    def test_phrase_goes_to_the_event_queue_cleaned_and_numbered(self) -> None:
        porta = self._server()
        code, body = self._req(porta, "POST", "/frase", {"testo": "  timer\n5   minuti "})
        self.assertEqual(code, 202)
        self.assertEqual(json.loads(body)["id"], 1)
        self.assertEqual(self.events.get_nowait(), Frase(1, "timer 5 minuti"))
        self.assertEqual(json.loads(self._req(porta, "POST", "/frase", {"testo": "luci"})[1])["id"], 2)

    def test_rejects_empty_or_oversized_phrases(self) -> None:
        porta = self._server()
        self.assertEqual(self._req(porta, "POST", "/frase", {"testo": "   "})[0], 400)
        self.assertEqual(self._req(porta, "POST", "/frase", {"testo": 5})[0], 400)
        self.assertEqual(self._req(porta, "POST", "/frase", {"testo": "x" * 3000})[0], 413)
        self.assertEqual(self._req(porta, "POST", "/altro", {"testo": "ciao"})[0], 404)
        self.assertTrue(self.events.empty())
        self.assertEqual(len(pulisci("a" * 500)), 200)

    def test_token_protects_the_api_but_not_the_page(self) -> None:
        porta = self._server(token="segreto")
        self.assertEqual(self._req(porta, "GET", "/")[0], 200)
        self.assertEqual(self._req(porta, "GET", "/stato")[0], 403)
        self.assertEqual(self._req(porta, "POST", "/frase", {"testo": "ciao"},
                                   {"X-Token": "sbagliato"})[0], 403)
        self.assertEqual(self._req(porta, "GET", "/stato?t=segreto")[0], 200)
        self.assertEqual(self._req(porta, "POST", "/frase", {"testo": "ciao"},
                                   {"X-Token": "segreto"})[0], 202)
        self.assertEqual(self.events.qsize(), 1)

    def test_address_for_the_qr(self) -> None:
        s = VoceServer({"token": "a b"}, self.events, dict)
        s.porta = 8443
        self.assertEqual(s.indirizzo("192.168.1.20"), "http://192.168.1.20:8443/?t=a%20b")
        s.https = True
        s.token = ""
        self.assertTrue(s.indirizzo("").endswith(".local:8443/"))

    def test_off_by_default(self) -> None:
        self.assertIsNone(avvia(DEFAULTS["voce"], self.events, dict, Path("non-usata")))

    def test_without_openssl_it_stays_on_http(self) -> None:
        def manca(*_: Any, **__: Any) -> None:
            raise FileNotFoundError("openssl")

        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(contesto_tls({}, Path(tmp), manca))

    def test_certificate_command_names_the_pi(self) -> None:
        visti: list[list[str]] = []

        def finto(cmd: list[str], **_: Any) -> None:
            visti.append(cmd)
            Path(cmd[cmd.index("-out") + 1]).write_text("c")
            Path(cmd[cmd.index("-keyout") + 1]).write_text("k")

        with tempfile.TemporaryDirectory() as tmp:
            cert, key = certificato(Path(tmp) / "voce", finto, host="pidash", ip="192.168.1.20")
            self.assertTrue(cert.is_file())
            self.assertEqual(key.stat().st_mode & 0o777, 0o600)
            san = next(a for a in visti[0] if a.startswith("subjectAltName="))
            self.assertEqual(san, "subjectAltName=DNS:pidash,DNS:pidash.local,DNS:localhost,"
                                  "IP:127.0.0.1,IP:192.168.1.20")
            certificato(Path(tmp) / "voce", finto)     # già presente: non si rifà
            self.assertEqual(len(visti), 1)

    @unittest.skipUnless(shutil.which("openssl"), "openssl non installato")
    def test_https_with_the_self_signed_certificate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                ctx = contesto_tls({}, Path(tmp))
            except subprocess.SubprocessError as exc:   # pragma: no cover - openssl rotto
                self.skipTest(str(exc))
            self.assertIsNotNone(ctx)
            s = VoceServer({}, self.events, lambda: {"id": 0}, ctx)
            self.servers.append(s)
            porta = s.avvia("127.0.0.1", 0)
            client = ssl.create_default_context(cafile=str(Path(tmp) / "cert.pem"))
            c = http.client.HTTPSConnection("localhost", porta, timeout=5, context=client)
            c.request("GET", "/stato")
            r = c.getresponse()
            self.assertEqual(r.status, 200)
            self.assertTrue(json.loads(r.read())["https"])
            c.close()


def _impronta(m: list[list[bool]]) -> str:
    return hashlib.sha1("".join("1" if c else "0" for r in m for c in r).encode()).hexdigest()


class TestQr(unittest.TestCase):
    """Matrici confrontate una volta con una libreria QR di riferimento e con un lettore (OpenCV)."""

    URL = "https://192.168.1.20:8443/?t=una-parola-a-caso"

    def test_known_matrices(self) -> None:
        self.assertEqual(_impronta(qr.codifica(self.URL)), "7075f834d73a1ef30b2450f67710132e23090687")
        self.assertEqual(_impronta(qr.codifica("pi-dash")), "f2258447cb431a523103afa962783a09f7048571")

    def test_smallest_version_and_finder_patterns(self) -> None:
        self.assertEqual(len(qr.codifica("pi-dash")), 21)          # versione 1
        self.assertEqual(len(qr.codifica(self.URL)), 29)           # versione 3
        self.assertEqual(len(qr.codifica("x" * 200, "M")), 57)     # versione 10
        m = qr.codifica(self.URL, "M")
        n = len(m)
        for cx, cy in ((0, 0), (n - 7, 0), (0, n - 7)):
            self.assertTrue(all(m[cy][cx + i] and m[cy + 6][cx + i] for i in range(7)))
            self.assertFalse(m[cy + 1][cx + 1])
            self.assertTrue(m[cy + 3][cx + 3])
        self.assertTrue(m[n - 8][8])                                 # modulo sempre scuro

    def test_too_long_or_bad_level(self) -> None:
        with self.assertRaises(ValueError):
            qr.codifica("x" * 400)
        with self.assertRaises(ValueError):
            qr.codifica("x", "H")


class TestVoceConfig(unittest.TestCase):
    def test_defaults_are_valid_and_bad_values_are_rejected(self) -> None:
        validate(td.make_cfg(), WIDGET_NAMES)
        validate(td.make_cfg(voce={"porta": 8443, "token": "abc"}), WIDGET_NAMES)
        for voce in ({"porta": "8443"}, {"porta": True}, {"porta": 70000}, {"token": 5},
                     {"key": "/k.pem"}):
            with self.subTest(voce=voce), self.assertRaises(ConfigError):
                validate(td.make_cfg(voce=voce), WIDGET_NAMES)


class TestVoceApp(unittest.TestCase):
    """Le frasi del telefono arrivano a Needle dal ciclo principale e l'esito torna al telefono."""

    def _app(self, pages: list[dict[str, str]]) -> App:
        cfg = td.make_cfg(pages=pages, needle={"regole": False}, voce={"porta": 8443})
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        main = Path(tmp) / "config.json"
        main.write_text("{}", encoding="utf-8")
        app = App(cfg, td.MemDisplay(480, 320), queue.Queue(), config_path=main)
        self.addCleanup(app.close)
        return app

    @staticmethod
    def _prepara(w: NeedleWidget) -> None:
        w.load_demo()
        w.demo = False
        w._checked = w._clock()     # niente controllo di rete durante il test
        w._post = lambda url, payload, timeout: (
            {} if url.endswith("/reset") else
            {"success": True, "confidence": 0.95,
             "function_calls": [{"name": "start_timer_minutes", "arguments": {"minutes": 5}}]})

    def _attendi(self, app: App, w: NeedleWidget) -> dict[str, Any]:
        td.TestNeedle._wait(w)
        for i in range(5):
            app.step(NOW, 0.1 * i, animate=False)
            s = app.voce_stato()
            if s["risposte"] > s["attesa"] and not s["lavora"]:
                return s
            time.sleep(0.01)
        self.fail("esito mai completo")

    def test_phrase_from_the_phone_runs_on_the_needle_page(self) -> None:
        app = self._app([{"name": "Home", "widget": "clock"}, {"name": "Needle", "widget": "needle"},
                         {"name": "+", "widget": "new"}])
        w = app.pages[1].widget
        assert isinstance(w, NeedleWidget)
        self._prepara(w)
        self.assertIs(app.needle(), w)
        app.events.put(Frase(7, "timer cinque minuti"))
        app.step(NOW, 0.0, animate=False)
        s = app.voce_stato()
        self.assertEqual((s["id"], s["accettata"]), (7, True))
        s = self._attendi(app, w)
        self.assertEqual((s["domanda"], s["esito"]), ("timer cinque minuti", "timer 5' avviato"))
        self.assertIsNotNone(app.find_page("timer"))

    def test_without_a_needle_page_a_hidden_one_answers(self) -> None:
        app = self._app([{"name": "Home", "widget": "clock"}, {"name": "+", "widget": "new"}])
        w = app.needle()
        self.assertNotIn(w, app.widgets.values())
        self._prepara(w)
        app.events.put(Frase(1, "timer cinque minuti"))
        app.step(NOW, 0.0, animate=False)
        s = self._attendi(app, w)
        self.assertEqual(s["esito"], "timer 5' avviato")
        self.assertEqual(app.page.kind, "timer")

    def test_a_second_phrase_while_busy_is_refused(self) -> None:
        app = self._app([{"name": "Needle", "widget": "needle"}, {"name": "+", "widget": "new"}])
        w = app.needle()
        self._prepara(w)
        w._busy = True
        app.events.put(Frase(3, "luci"))
        app.step(NOW, 0.0, animate=False)
        self.assertEqual((app.voce_stato()["id"], app.voce_stato()["accettata"]), (3, False))
        w._busy = False

    def test_tap_on_the_bot_shows_the_qr_of_the_page(self) -> None:
        app = self._app([{"name": "Needle", "widget": "needle"}, {"name": "+", "widget": "new"}])
        w = app.needle()
        w.load_demo()
        box = Box(0, 0, 480, 200)
        self.assertNotIn("qr", [h for _, h in needle_page.hits(box, w, 1.0)])   # senza indirizzo
        w.on_hit("qr", NOW)
        self.assertFalse(w.qr_visibile())
        app.imposta_voce_url(TestQr.URL)
        app.add_page("needle")                             # anche le schede nuove lo ricevono
        self.assertEqual(app.pages[1].widget.voce_url, TestQr.URL)
        self.assertEqual(needle_page.hits(box, w, 1.0)[-1][1], "qr")
        bot = app.step(NOW, 0.0, animate=False)
        w.on_hit("qr", NOW)
        self.assertTrue(w.qr_visibile())
        self.assertEqual(len(w.qr_moduli()), 29)
        con_qr = app.step(NOW, 0.1, animate=False)
        assert bot is not None and con_qr is not None
        self.assertNotEqual(bot.tobytes(), con_qr.tobytes())
        w.on_hit("qr", NOW)                                 # secondo tocco: torna il bot
        self.assertFalse(w.qr_visibile())

    def test_off_by_default_no_hidden_widget(self) -> None:
        cfg = copy.deepcopy(DEFAULTS)
        cfg = _merge(cfg, {"pages": [{"name": "Home", "widget": "clock"}], "weather": {"demo": True}})
        app = App(cfg, td.MemDisplay(480, 320), queue.Queue())
        self.addCleanup(app.close)
        self.assertIsNone(app._needle_voce)


if __name__ == "__main__":
    unittest.main()
