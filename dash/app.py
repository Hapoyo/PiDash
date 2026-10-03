"""Dashboard in esecuzione: pagine dello schedario, eventi, ciclo di aggiornamento."""
from __future__ import annotations

import logging
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image

from . import __version__, azioni
from .backlight import Backlight
from .power import PowerMonitor
from .config import save_local
from .display import Display
from .hue import Hue
from .inputs import Buzzer, Event, Tap, panel_to_frame
from .motion import Motion
from .voce import Frase
from .widgets import ETICHETTE, WIDGET_NAMES, Widget, WidgetFactory
from .widgets.alarm import AlarmWidget
from .widgets.calibrate import TouchWizard
from .widgets.needle import NeedleWidget
from .widgets.new import NewWidget

log = logging.getLogger("dash")

TAP_TOLERANCE = 12  # pixel a 480×320: un tocco appena fuori da un bottone vale per il più vicino
NOTICE_S = 4.0      # durata dei messaggi brevi nelle Impostazioni


@dataclass
class Page:
    """Una cartella dello schedario: nome sulla linguetta e widget che ne fornisce i dati."""
    name: str
    widget: Widget
    key: str = ""      # identificatore univoco (es. "timer#2"): più pagine dello stesso tipo
    kind: str = ""     # tipo di widget della pagina


class App:
    """Stato del dashboard e ciclo di aggiornamento."""

    def __init__(self, cfg: dict[str, Any], display: Display, events: queue.Queue[Any],
                 config_path: Path | None = None) -> None:
        self.cfg = cfg
        self.display = display
        self.events = events
        self.config_path = config_path  # dove salvare le pagine create dalla scheda "+"
        self.factory = WidgetFactory(cfg)
        self.hue = Hue(cfg.get("hue") or {}, on_trovato=self._bridge_trovato)   # luci di casa, comandate da Needle
        # la retroilluminazione vera solo sul Pi: nel simulatore si scurisce l'immagine
        bl = dict(cfg.get("backlight") or {})
        if cfg["display"]["driver"] != "fb":
            bl["mode"] = "sw"
        self.backlight = Backlight.from_cfg(bl)
        power = dict(cfg.get("power") or {})
        if cfg["display"]["driver"] != "fb":
            power["monitor"] = False  # il PC non ha il rilevatore del Raspberry
        self.power = PowerMonitor(power)
        self.calib: TouchWizard | None = None   # calibrazione del touch in corso
        self.shutting_down = False
        self.run_cmd: Any = subprocess.run       # sostituibile nei test
        self._power_thread: threading.Thread | None = None
        self._power_sent = False                  # comando di spegnimento già lanciato
        self._notice = ("", 0.0)
        self.voce_url = ""     # pagina "premi e parla" (`dash/voce.py`): le schede Needle la mostrano in QR
        self.pages: list[Page] = []
        self.widgets: dict[str, Widget] = {}
        for p in cfg["pages"]:
            self._new_page(p["widget"], p["name"])
        self.page_idx = 0
        self.buzzer = Buzzer(cfg["input"].get("buzzer_pin"), bool(cfg["input"].get("sound")))
        self._stop = threading.Event()
        self.buttons: list[Any] = []  # riferimenti ai pulsanti GPIO (evita il GC)
        self._last_key: Any = None
        self.touch = False  # True se il touchscreen è attivo (cambia il testo dell'allarme)
        self.touch_cal: Any = None  # TouchCalibration in uso, per la calibrazione a schermo
        self._renderer: Any = None
        self.motion = Motion.from_cfg(cfg.get("motion") or {})
        self._base: Image.Image | None = None    # pagina ferma, ridisegnata solo se cambiano i dati
        self._frame: Image.Image | None = None   # ultimo fotogramma mostrato (prima della rotazione)
        self._shown_page = -1
        self._last_fkey: int | None = None
        # frasi dal telefono (`dash/voce.py`): Needle che le riceve e ultima frase gestita
        self._needle_voce: NeedleWidget | None = None    # se non c'è nessuna scheda Needle
        self._voce: NeedleWidget | None = self.needle() if (cfg.get("voce") or {}).get("porta") else None
        self._voce_ultima = (0, False, 0)                 # (numero, accettata, risposte prima)

    @property
    def page(self) -> Page:
        return self.pages[self.page_idx]

    # --- pagine ----------------------------------------------------------
    def _new_page(self, kind: str, name: str, at: int | None = None) -> Page:
        """Crea la pagina e il suo widget; `at` la inserisce prima di quella posizione."""
        key, n = kind, 1
        while key in self.widgets:  # chiave libera anche dopo aver tolto pagine dello stesso tipo
            n += 1
            key = f"{kind}#{n}"
        page = Page(name, self.factory.make(kind), key, kind)
        if isinstance(page.widget, NewWidget):  # la scheda "+" agisce sullo schedario
            page.widget.pagine = self.page_kinds
            page.widget.aggiungi = self.add_page
            page.widget.togli = self.remove_page
            page.widget.luce = lambda: self.backlight.level
            page.widget.regola_luce = self.adjust_light
            page.widget.calibra = self.start_calibration
            page.widget.spegni = self.power_off
            page.widget.avviso = self.notice
            page.widget.info = self.info
            page.widget.alimentazione = lambda: self.power
        if isinstance(page.widget, NeedleWidget):   # per capire "luce del soggiorno" servono i nomi
            page.widget.stanze = self._nomi_stanze
            page.widget.voce_url = self.voce_url
        self.pages.insert(len(self.pages) if at is None else at, page)
        self.widgets[key] = page.widget
        return page

    def _nomi_stanze(self) -> list[str] | None:
        """Stanze del bridge Hue per l'interprete di frasi; None se Hue non c'è (HueError: bridge muto)."""
        if not self.hue.configurato:
            return None
        return [s.nome for s in self.hue.stanze()]

    def needle(self) -> NeedleWidget:
        """Needle per le frasi dal telefono: quello della prima scheda Needle, altrimenti uno
        senza scheda (le azioni funzionano lo stesso, il risultato si vede sul telefono)."""
        for p in self.pages:
            if isinstance(p.widget, NeedleWidget):
                return p.widget
        if self._needle_voce is None:
            widget = self.factory.make("needle")
            assert isinstance(widget, NeedleWidget)
            widget.stanze = self._nomi_stanze
            self._needle_voce = widget
        return self._needle_voce

    def imposta_voce_url(self, url: str) -> None:
        """Indirizzo della pagina "premi e parla": le schede Needle lo mostrano in QR."""
        self.voce_url = url
        for widget in list(self.widgets.values()) + ([self._needle_voce] if self._needle_voce else []):
            if isinstance(widget, NeedleWidget):
                widget.voce_url = url

    def handle_frase(self, frase: Frase) -> None:
        """Frase dal telefono: a Needle, come un tocco su una frase della scheda."""
        widget = self._voce = self.needle()
        prima = widget.risposte
        self._voce_ultima = (frase.id, widget.chiedi(frase.testo), prima)

    def voce_stato(self) -> dict[str, Any]:
        """Stato per la pagina del telefono; chiamato dal thread del server (solo dati con lock)."""
        widget, (n, accettata, prima) = self._voce, self._voce_ultima
        if widget is None:
            return {"id": n, "accettata": accettata, "attesa": prima, "risposte": 0, "lavora": False,
                    "stato": "controllo…", "domanda": "", "esito": "", "errore": "", "chiamate": [],
                    "frasi": []}
        last = widget.snapshot()[2]
        return {"id": n, "accettata": accettata, "attesa": prima, "risposte": widget.risposte,
                "lavora": widget.in_attesa(), "stato": widget.stato(),
                "domanda": last.domanda if last else "", "esito": last.esito if last else "",
                "errore": last.errore if last else "",
                "chiamate": list(last.chiamate) if last else [], "frasi": list(widget.queries)}

    def page_kinds(self) -> dict[str, str]:
        """{tipo: chiave} delle pagine presenti, per l'interruttore della scheda "+"."""
        return {p.kind: p.key for p in self.pages if p.kind != "new"}

    def add_page(self, kind: str) -> None:
        """Aggiunge una pagina del tipo indicato prima della scheda "+" e ci si sposta."""
        if kind not in WIDGET_NAMES or kind == "new":
            log.warning("tipo di pagina sconosciuto: %s", kind)
            return
        base = ETICHETTE.get(kind, kind.capitalize())
        nomi = {p.name for p in self.pages}
        name, n = base, 1
        while name in nomi:
            n += 1
            name = f"{base} {n}"
        at = next((i for i, p in enumerate(self.pages) if p.kind == "new"), len(self.pages))
        self._new_page(kind, name, at)
        self.page_idx = at
        self._save_pages()

    def find_page(self, kind: str) -> Page | None:
        """La prima pagina del tipo dato, se c'è."""
        return next((p for p in self.pages if p.kind == kind), None)

    def open_kind(self, kind: str) -> bool:
        """Apre la prima pagina del tipo dato; False se non c'è."""
        idx = next((i for i, p in enumerate(self.pages) if p.kind == kind), None)
        if idx is not None:
            self._goto(idx)
        return idx is not None

    def restore_page(self, page: Page) -> None:
        """Torna a una pagina già aperta (dopo che un'azione ne ha creata un'altra)."""
        idx = next((i for i, p in enumerate(self.pages) if p is page), None)
        if idx is not None:
            self._goto(idx)

    def save_alarms(self, widget: AlarmWidget) -> None:
        """Salva le sveglie in config.local.json, così sopravvivono al riavvio."""
        self.cfg["alarm"]["alarms"] = [a.to_cfg() for a in widget.alarms]
        self._save_local({"alarm": {"alarms": self.cfg["alarm"]["alarms"]}}, "sveglie")

    def remove_page(self, key: str) -> None:
        """Toglie una pagina creata in precedenza; l'ultima rimasta non si può togliere."""
        idx = next((i for i, p in enumerate(self.pages) if p.key == key), None)
        if idx is None or len(self.pages) <= 1 or self.pages[idx].kind == "new":
            return
        corrente = self.page
        page = self.pages.pop(idx)
        self.widgets.pop(page.key, None)
        page.widget.close()
        # si resta sulla pagina aperta (di norma la scheda "+"), non su quella che ha preso il suo posto
        self.page_idx = next((i for i, p in enumerate(self.pages) if p is corrente),
                             min(self.page_idx, len(self.pages) - 1))
        self._save_pages()

    def _save_pages(self) -> None:
        """Salva lo schedario in config.local.json, così sopravvive al riavvio."""
        self.cfg["pages"] = [{"name": p.name, "widget": p.kind} for p in self.pages]
        if self.config_path is None:
            return
        try:
            save_local(self.config_path, {"pages": self.cfg["pages"]})
        except OSError as exc:
            log.error("pagine non salvate: %s", exc)

    # --- impostazioni ----------------------------------------------------
    def notify(self, text: str) -> None:
        """Messaggio breve nella riga di stato delle Impostazioni."""
        self._notice = (text, time.monotonic() + NOTICE_S)
        log.info("[avviso] %s", text)

    def notice(self) -> str:
        text, until = self._notice
        return text if time.monotonic() < until else ""

    def info(self) -> str:
        luce = "retroilluminazione" if self.backlight.hardware else "luce software"
        return f"pi-dash v{__version__} · {luce}"

    def adjust_light(self, delta: int) -> None:
        """Luminosità ± (10…100 %), salvata in config.local.json."""
        level = self.backlight.step(delta)
        self.cfg.setdefault("backlight", {})["level"] = level
        self._save_local({"backlight": {"level": level}}, "luminosità")

    def _bridge_trovato(self, bridge: str) -> None:
        """Il bridge Hue ha cambiato indirizzo: lo ricorda anche dopo il riavvio."""
        self.cfg.setdefault("hue", {})["bridge"] = bridge
        self._save_local({"hue": {"bridge": bridge}}, "indirizzo del bridge")

    def _save_local(self, changes: dict[str, Any], what: str) -> None:
        if self.config_path is None:
            return
        try:
            save_local(self.config_path, changes)
        except OSError as exc:
            log.error("%s non salvata: %s", what, exc)

    def start_calibration(self) -> None:
        self.calib = TouchWizard(self.cfg["display"]["rotate"])

    def _calibration_tap(self, tap: Tap) -> None:
        assert self.calib is not None
        if not self.calib.add(tap):
            return
        result = self.calib.result()
        self.calib = None
        if result is None:
            self.notify("calibrazione non riuscita: riprova toccando le croci")
            return
        touch = self.cfg["input"].setdefault("touch", {})
        touch.update(result)
        if self.touch_cal is not None:
            self.touch_cal.apply(touch)
        self._save_local({"input": {"touch": result}}, "calibrazione")
        self.notify("touch calibrato")

    def power_off(self) -> None:
        """Spegne il Raspberry: schermata di spegnimento, poi il comando in `power.cmd`."""
        cmd = (self.cfg.get("power") or {}).get("cmd")
        if self.cfg["display"]["driver"] != "fb" or not cmd:
            log.info("[spegni] simulato: %s", " ".join(cmd or []))
            self.notify("spegnimento simulato (solo sul raspberry)")
            return
        self.shutting_down = True  # il comando parte dopo aver mostrato la schermata
        self._power_sent = False

    def _run_power_off(self, cmd: list[str]) -> None:
        try:
            r = self.run_cmd(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                raise OSError((r.stderr or "").strip() or f"codice {r.returncode}")
            log.info("spegnimento avviato")
        except (OSError, subprocess.SubprocessError) as exc:
            log.error("spegnimento non riuscito (%s): %s", " ".join(cmd), exc)
            self.shutting_down = False
            self.notify("spegni non consentito: vedi scripts/installa-servizio.sh")

    # --- eventi ----------------------------------------------------------
    def alerting(self) -> tuple[Widget, str] | None:
        for w in self.widgets.values():
            msg = w.alert()
            if msg:
                return w, msg
        return None

    def handle(self, ev: Event, now: datetime) -> None:
        if self.motion.boot_start is not None and ev is not Event.QUIT:
            self.motion.skip_boot()  # un tasto durante l'avvio lo salta e basta
            return
        if ev is Event.QUIT:
            self._stop.set()
        elif ev is Event.NEXT:
            self._goto(self.page_idx + 1)
        elif ev in (Event.ACTION, Event.BACK):
            alert = self.alerting()
            target = alert[0] if alert and ev is Event.ACTION else self.page.widget
            (target.on_action if ev is Event.ACTION else target.on_back)(now)

    def frame_size(self) -> tuple[int, int]:
        """Dimensioni del fotogramma disegnato (prima della rotazione verso il pannello)."""
        d = self.cfg["display"]
        return (d["height"], d["width"]) if d["rotate"] in (90, 270) else (d["width"], d["height"])

    @property
    def renderer(self) -> Any:
        if self._renderer is None:
            from .render import CyberRenderer
            self._renderer = CyberRenderer(self.cfg["theme"].get("palette"))
        return self._renderer

    def _goto(self, idx: int) -> None:
        self.page_idx = idx % len(self.pages)

    def handle_tap(self, tap: Tap, now: datetime) -> None:
        """Linguetta → apre quella cartella; bottone → la sua azione; resto → azione del widget."""
        if self.motion.boot_start is not None:
            self.motion.skip_boot()
            return
        if self.shutting_down:
            return
        if self.calib is not None:
            self._calibration_tap(tap)
            return
        fx, fy = panel_to_frame(tap.x, tap.y, self.cfg["display"]["rotate"])
        w, h = self.frame_size()
        px, py = fx * w, fy * h
        alert = self.alerting()
        if alert:  # qualsiasi tocco spegne sveglia/timer
            alert[0].on_action(now)
            return
        for i, b in enumerate(self.renderer.nav_rows(self)):
            if b.x <= px < b.right and b.y <= py < b.bottom:
                self._goto(i)
                return
        hit = self.hit_at(px, py)
        if hit is not None:
            self.page.widget.on_hit(hit, now)
        elif self.page.widget.has_action and self.page.widget.tap_action:
            self.page.widget.on_action(now)

    def hit_at(self, px: float, py: float) -> str | None:
        """Bottone sotto il dito; se nessuno, il più vicino entro `TAP_TOLERANCE`."""
        best, best_d = None, float("inf")
        tol = TAP_TOLERANCE * min(self.frame_size()[0] / 480, self.frame_size()[1] / 320)
        for b, hit in self.renderer.hit_boxes(self):
            dx = max(b.x - px, 0.0, px - b.right)
            dy = max(b.y - py, 0.0, py - b.bottom)
            d = (dx * dx + dy * dy) ** 0.5
            if d == 0:
                return hit
            if d <= tol and d < best_d:
                best, best_d = hit, d
        return best

    def stop(self) -> None:
        self._stop.set()

    # --- disegno ---------------------------------------------------------
    def _rotated(self, img: Image.Image) -> Image.Image:
        rotate = self.cfg["display"]["rotate"]
        return img.rotate(-rotate, expand=True) if rotate else img

    def render(self, now: datetime) -> Image.Image:
        """Fotogramma fermo della pagina corrente (immagine RGB), già ruotato per il pannello."""
        return self._rotated(self.renderer.render(self, now))

    # --- ciclo -----------------------------------------------------------
    def step(self, now: datetime, t: float, animate: bool = True) -> Image.Image | None:
        """Un giro del ciclo: eventi, dati, disegno. Restituisce il fotogramma mostrato, se c'è.

        La pagina base si ridisegna solo quando cambiano i dati (`state_key`); con le animazioni
        attive si mostrano in più `motion.fps` fotogrammi al secondo composti sopra di essa.
        """
        while True:
            try:
                ev = self.events.get_nowait()
            except queue.Empty:
                break
            if isinstance(ev, Tap):
                self.handle_tap(ev, now)
            elif isinstance(ev, Frase):
                self.handle_frase(ev)
            else:
                self.handle(ev, now)
        extra = [self._needle_voce] if self._needle_voce is not None else []
        for widget in list(self.widgets.values()) + extra:   # le funzioni di Needle cambiano le pagine
            if isinstance(widget, NeedleWidget):
                for nome, args, frase in widget.take_calls():
                    widget.set_esito(azioni.esegui(self, nome, args, widget.naviga, frase))
        for widget in list(self.widgets.values()) + extra:
            widget.update(now)
        self.power.sample(now, t)
        if self.calib is not None and self.calib.expired():
            self.calib = None
            self.notify("calibrazione annullata")
        alert = self.alerting()
        self.buzzer.set(alert is not None)
        if animate and self.page_idx != self._shown_page:
            self.motion.page_changed(self._frame, t)  # scansione dalla pagina di prima
        self._shown_page = self.page_idx
        key = (self.page_idx, tuple(self.widgets), now.strftime("%Y%m%d%H%M"),
               alert[1] if alert else None, self.backlight.level, self.shutting_down,
               self.calib.step if self.calib is not None else None, self.power.state_key(),
               tuple(w.state_key(now) for w in self.widgets.values()))
        dirty = key != self._last_key
        if dirty:                          # dati cambiati: nuova pagina base
            self._base = self.renderer.render(self, now)
            if animate:
                self.motion.slots_drawn(self.renderer.slots, t)
            self._last_key = key
        fkey = self.motion.frame_key(t) if animate else None
        if self._base is None or not (dirty or fkey != self._last_fkey):
            return None
        self._last_fkey = fkey
        self._frame = (self.renderer.compose(self._base, self, self.motion, t) if animate
                       else self._base)
        shown = self.backlight.apply(self._rotated(self._frame))
        self.display.show(shown)
        if self.shutting_down and not self._power_sent:  # schermata già sul pannello
            self._power_sent = True
            cmd = list(self.cfg["power"]["cmd"])
            self._power_thread = threading.Thread(target=self._run_power_off, args=(cmd,),
                                                  name="spegni", daemon=True)
            self._power_thread.start()
        return shown

    def run(self, once: bool = False, clock: Any = time.monotonic) -> None:
        """Ciclo principale; `once` disegna un solo fotogramma fermo (niente animazioni)."""
        idle = self.cfg["display"]["tick_s"]
        if not once:
            self.motion.start(clock())
        while not self._stop.is_set():
            t = clock()
            self.step(datetime.now(), t, animate=not once)
            if once:
                break
            # il tempo di disegno conta: si aspetta solo ciò che manca al prossimo fotogramma
            self._stop.wait(max(0.0, self.motion.interval(t, idle) - (clock() - t)))

    def close(self) -> None:
        for widget in list(self.widgets.values()) + ([self._needle_voce] if self._needle_voce else []):
            widget.close()
        self.buzzer.set(False)
        self.display.close()
