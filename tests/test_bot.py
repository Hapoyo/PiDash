"""Bot animato di Needle: facce, animazione, geometria: python -m unittest -v"""
from __future__ import annotations

import queue
import unittest
from datetime import datetime

from PIL import Image, ImageChops

from dash.app import App
from dash.layout import Box
from dash.render import bot
from dash.render.canvas import Canvas
from dash.render.pages import needle
from dash.render.theme import unit
from dash.widgets.needle import NeedleWidget
from tests.test_dash import MemDisplay, make_cfg

NOW = datetime(2026, 9, 24, 7, 42)


def _canvas() -> Canvas:
    from dash.render.renderer import CyberRenderer
    return Canvas(Image.new("RGB", (160, 160), CyberRenderer().c["cream"]), CyberRenderer().c, 1.0)


def _faccia(umore: str, t: float = 0.0) -> Image.Image:
    cv = _canvas()
    bot.draw(cv, Box(20, 20, 120, 120), umore, t, "cream")
    return cv.img


class TestBot(unittest.TestCase):
    def test_every_mood_has_its_own_face(self) -> None:
        facce = {m: _faccia(m).tobytes() for m in bot.MOODS}
        self.assertEqual(len(set(facce.values())), len(bot.MOODS))

    def test_unknown_mood_draws_the_ready_face(self) -> None:
        self.assertEqual(_faccia("sconosciuto").tobytes(), _faccia("pronto").tobytes())

    def test_faces_move_over_time(self) -> None:
        for umore in ("controllo", "pronto", "penso", "fatto", "dubbio", "errore", "offline"):
            visti = {_faccia(umore, t / 10).tobytes() for t in range(1, 40)}
            self.assertGreater(len(visti), 1, umore)

    def test_ready_bot_blinks(self) -> None:
        aperti, chiusi = _faccia("pronto", 1.0), _faccia("pronto", bot.SBATTE_S - 0.05)
        self.assertNotEqual(aperti.tobytes(), chiusi.tobytes())
        # a palpebre chiuse gli occhi (ambra) sono molto meno estesi
        ambra = (0xf2, 0xbb, 0x5b)
        self.assertGreater(sum(1 for p in aperti.getdata() if p == ambra),
                           3 * sum(1 for p in chiusi.getdata() if p == ambra))

    def test_every_face_stays_inside_its_box(self) -> None:
        for umore in bot.MOODS:
            for t in (0.0, 0.7, 1.3, 2.9):
                bb = ImageChops.difference(_faccia(umore, t), _canvas().img).getbbox()
                assert bb is not None
                # il riquadro è (20, 20)–(140, 140): niente esce, nemmeno scuotendo la testa
                self.assertTrue(bb[0] >= 19 and bb[1] >= 19 and bb[2] <= 141 and bb[3] <= 141,
                                (umore, t, bb))
            self.assertEqual(_faccia(umore).tobytes(), _faccia(umore).tobytes())     # deterministica

    def test_non_square_box_is_centred(self) -> None:
        cv = _canvas()
        bot.draw(cv, Box(0, 0, 160, 80), "pronto", 0.0, "cream")      # il lato minore è 80
        bb = ImageChops.difference(cv.img, _canvas().img).getbbox()
        assert bb is not None
        self.assertTrue(bb[0] >= 40 - 1 and bb[2] <= 120 + 1 and bb[3] <= 80 + 1, bb)


class TestPaginaNeedle(unittest.TestCase):
    def _app(self, livello: str = "pieno") -> tuple[App, NeedleWidget]:
        cfg = make_cfg(pages=[{"name": "Needle", "widget": "needle"}], motion={"livello": livello})
        app = App(cfg, MemDisplay(480, 320), queue.Queue())
        w = app.page.widget
        assert isinstance(w, NeedleWidget)
        w.load_demo()
        return app, w

    def test_page_registers_the_bot_effect_with_the_mood(self) -> None:
        app, w = self._app()
        for umore in bot.MOODS:
            w.umore_forzato = umore
            app.renderer.render(app, NOW)
            fx = [e for e in app.renderer.fx if e.kind == "bot"]
            self.assertEqual(len(fx), 1)
            self.assertEqual(bot.MOODS[int(fx[0].extra[0])], umore)
        app.close()

    def test_bot_is_animated_only_at_full_motion(self) -> None:
        app, w = self._app()
        w.umore_forzato = "penso"
        base = app.renderer.render(app, NOW)
        a = app.renderer.compose(base, app, app.motion, 10.0)
        b = app.renderer.compose(base, app, app.motion, 10.5)
        self.assertNotEqual(a.tobytes(), b.tobytes())              # il bot si muove
        box = next(e.box for e in app.renderer.fx if e.kind == "bot")
        # fuori dal riquadro del bot i due fotogrammi sono uguali
        for img in (a, b):
            img.paste(base.crop(box), box[:2])
        self.assertEqual(ImageChops.difference(a, b).getbbox(), None)
        app.motion.livello = "eventi"
        fermo = app.renderer.compose(base, app, app.motion, 10.0)
        self.assertEqual(fermo.tobytes(), base.tobytes())          # senza "pieno" resta la faccia ferma
        app.close()

    def test_page_redraws_when_the_mood_changes(self) -> None:
        app, w = self._app()
        w.umore_forzato = "penso"
        k1 = w.state_key(NOW)
        w.umore_forzato = "fatto"
        self.assertNotEqual(k1, w.state_key(NOW))
        app.close()

    def test_geometry_of_buttons_is_still_shared(self) -> None:
        app, w = self._app()
        w.umore_forzato = "errore"
        app.renderer.render(app, NOW)
        boxes = needle.hits(app.renderer.content_inner(app), w, unit(480, 320))
        self.assertEqual(len(boxes), len(w.queries))
        page = app.renderer.content_inner(app)
        panel = needle._geometry(page, unit(480, 320))[0]
        # i bottoni stanno a destra del pannello del bot, dentro la pagina
        self.assertTrue(all(b.x >= panel.right and b.right <= page.right and b.bottom <= page.bottom
                            for b, _ in boxes))
        bot_box = next(e.box for e in app.renderer.fx if e.kind == "bot")
        self.assertGreater(bot_box[3] - bot_box[1], page.h * 0.6)    # il bot è grande
        app.close()


if __name__ == "__main__":
    unittest.main()
