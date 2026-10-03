"""Funzioni che Needle può far eseguire al dashboard: `needle/tools.json` le dichiara, qui si eseguono.

Il modello propone, il dashboard decide: ogni azione controlla gli argomenti (minuti e orari
entro limiti, pagine da una lista fissa, stanze del bridge Hue) e non fa mai nulla di
irreversibile (niente spegnimento del Pi). Si eseguono nel ciclo principale (`App.step`), mai nel
thread della richiesta.

Le funzioni sono pensate per un modello da 35 MB, che copia il numero dalla frase senza
convertire le unità e capisce poco l'italiano: una funzione per unità di tempo
(`start_timer_minutes`, `start_timer_seconds`) e una senza argomenti per ogni pagina (`open_*`)
danno risposte molto più affidabili di un'unica `start_timer(minutes)` e di `show_page(page)`.
Per le luci il modello confonde "accendi" e "spegni" (con "accendi tutte le luci" sceglie
`lights_off`) e inventa numeri: il verso lo decide quindi il verbo della frase e la luminosità
deve comparire nel testo (`_verso`, `_numero_nel_testo`).
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Callable

from .location import NET_ERRORS, geocode
from .hue import COLORI, TEMPERATURE, HueError, Stanza
from .widgets.alarm import AlarmWidget
from .widgets.timer import TimerWidget
from .widgets.weather import WeatherWidget

if TYPE_CHECKING:
    from .app import App, Page

MAX_TIMER_MIN = 180
GEOCODING_S = 6   # attesa massima della ricerca di una città (gira nel ciclo principale)
# Funzione open_<nome> → (tipo di widget, nome mostrato).
PAGINE = {"home": ("clock", "home"), "weather": ("weather", "meteo"), "timer": ("timer", "timer"),
          "alarm": ("alarm", "sveglia"), "system": ("system", "sistema"),
          "settings": ("new", "impostazioni")}
ACCENDI = re.compile(r"\b(accend|attiv|illumin)\w*")
SPEGNI = re.compile(r"\b(spegn|disattiv|oscur)\w*")
NEGAZIONE = re.compile(r"\b(non|senza|mai)\b")
PERCENTO = re.compile(r"\b(\d{1,3})\s*(?:%|per\s*cento)")
MASSIMO = re.compile(r"\b(?:al\s+massimo|massim[oa])\b")

Esito = tuple[str, str]  # (frase per lo schermo, tipo di pagina da aprire, "" se nessuna)
Azione = Callable[["App", dict[str, Any], str], Esito]  # (app, argomenti, frase detta)


class AzioneError(ValueError):
    """Argomenti non validi o funzione non eseguibile: il testo finisce sullo schermo."""


def _pagina(app: App, kind: str) -> Page:
    """La pagina del tipo dato; se manca la crea (come il tocco su "+" nelle Impostazioni)."""
    page = app.find_page(kind)
    if page is None:
        app.add_page(kind)
        page = app.find_page(kind)
    if page is None:
        raise AzioneError(f"pagina {kind} non disponibile")
    return page


def _timer(campo: str, secondi: int) -> Azione:
    """Timer con la durata nell'argomento `campo` (in unità da `secondi` secondi ciascuna)."""
    def azione(app: App, args: dict[str, Any], frase: str) -> Esito:
        try:
            durata = float(args[campo]) * secondi
        except (KeyError, TypeError, ValueError) as exc:
            raise AzioneError("durata non valida") from exc
        if not 1 <= durata <= MAX_TIMER_MIN * 60:  # falso anche per NaN
            raise AzioneError(f"timer da 1 s a {MAX_TIMER_MIN}'")
        widget = _pagina(app, "timer").widget
        assert isinstance(widget, TimerWidget)
        widget.start_for(round(durata))
        m, s = divmod(round(durata), 60)
        tempo = f"{m}'" if not s else (f"{s}\"" if not m else f"{m}'{s:02d}\"")
        return f"timer {tempo} avviato", "timer"
    return azione


def _orario(args: dict[str, Any]) -> tuple[int, int]:
    try:
        hh, mm = (int(p) for p in str(args["time"]).split(":"))
    except (KeyError, ValueError) as exc:
        raise AzioneError("orario non valido (serve HH:MM)") from exc
    if not (0 <= hh < 24 and 0 <= mm < 60):
        raise AzioneError("orario non valido (serve HH:MM)")
    return hh, mm


def _sveglia(app: App, args: dict[str, Any], frase: str) -> Esito:
    hh, mm = _orario(args)      # prima di creare la pagina: un rifiuto non lascia tracce
    giorni: frozenset[int] | None = None
    if args.get("days") is not None:
        try:
            giorni = frozenset(int(d) for d in args["days"])
        except (TypeError, ValueError) as exc:
            raise AzioneError("giorni non validi") from exc
        if not giorni or not giorni <= frozenset(range(7)):
            raise AzioneError("giorni non validi")
    widget = _pagina(app, "alarm").widget
    assert isinstance(widget, AlarmWidget)
    try:
        sveglia = widget.add_alarm(hh, mm, giorni)
    except ValueError as exc:   # per esempio troppe sveglie
        raise AzioneError(str(exc)) from exc
    app.save_alarms(widget)
    quando = "ogni giorno" if sveglia.days == frozenset(range(7)) else sveglia.label_days().lower()
    return f"sveglia {hh:02d}:{mm:02d} {quando}", "alarm"


def _togli_sveglia(app: App, args: dict[str, Any], frase: str) -> Esito:
    """Toglie la sveglia a quell'ora, o tutte se l'orario non c'è."""
    pagina = app.find_page("alarm")
    if pagina is None:
        raise AzioneError("nessuna sveglia")
    widget = pagina.widget
    assert isinstance(widget, AlarmWidget)
    hh, mm = _orario(args) if args.get("time") else (None, None)
    tolte = widget.remove_alarms(hh, mm)
    if not tolte:
        raise AzioneError(f"nessuna sveglia alle {hh:02d}:{mm:02d}" if hh is not None else "nessuna sveglia")
    app.save_alarms(widget)
    if hh is not None:
        return f"sveglia {hh:02d}:{mm:02d} tolta", "alarm"
    return ("sveglia tolta" if tolte == 1 else f"{tolte} sveglie tolte"), "alarm"


def _comando_timer(metodo: str, testo: str, vuoto: str) -> Azione:
    """Ferma, mette in pausa o riprende il timer (`TimerWidget.<metodo>`)."""
    def azione(app: App, args: dict[str, Any], frase: str) -> Esito:
        pagina = app.find_page("timer")
        if pagina is None:
            raise AzioneError("nessun timer")
        widget = pagina.widget
        assert isinstance(widget, TimerWidget)
        if not getattr(widget, metodo)():
            raise AzioneError(vuoto)
        return testo, "timer"
    return azione


def _apri(kind: str, nome: str) -> Azione:
    """Apre una pagina già presente (non se ne aggiungono per un "apri")."""
    def azione(app: App, args: dict[str, Any], frase: str) -> Esito:
        if app.find_page(kind) is None:
            raise AzioneError(f"pagina {nome} non presente")
        return f"apro {nome}", kind
    return azione


def _meteo(app: App, args: dict[str, Any], frase: str) -> Esito:
    _pagina(app, "weather")
    # il meteo è quello del luogo del dashboard: per un'altra città si dice, non si finge
    return ("apro il meteo (luogo del dashboard)" if args.get("city") else "apro il meteo"), "weather"


def _citta_meteo(app: App, args: dict[str, Any], frase: str) -> Esito:
    """"Meteo Roma": la scheda meteo mostra quella città, senza toccare la posizione del dashboard.

    Temporanea: dura fino al riavvio o a "meteo qui" (`city` vuota). Se la città non esiste o la
    rete manca il meteo resta com'era e il motivo va sullo schermo.
    """
    citta = str(args.get("city") or "").strip()
    widget = _pagina(app, "weather").widget
    assert isinstance(widget, WeatherWidget)
    if not citta:
        widget.clear_city()
        return "meteo del dashboard", "weather"
    try:
        trovata = geocode(citta, timeout=GEOCODING_S)
    except NET_ERRORS as exc:
        raise AzioneError(f"ricerca di {citta} non riuscita (rete)") from exc
    if trovata is None:
        raise AzioneError(f"città non trovata: {citta}")
    widget.set_city(*trovata)
    return f"meteo di {trovata[0].lower()}", "weather"


# --- luci Philips Hue -------------------------------------------------------
def _verso(frase: str) -> bool:
    """Accendere o spegnere: lo decide il verbo della frase, non il modello.

    Serve un verbo univoco e nessuna negazione ("non accendere"); se la frase non dice niente
    ("luce del soggiorno") non si esegue, anche se il modello ha proposto qualcosa.
    """
    testo = frase.lower()
    if NEGAZIONE.search(testo):
        raise AzioneError("frase con negazione: non eseguo")
    accendi, spegni = bool(ACCENDI.search(testo)), bool(SPEGNI.search(testo))
    if accendi == spegni:   # nessun verbo, oppure tutti e due
        raise AzioneError("accendi o spegni? non eseguo")
    return accendi


def _numero_nel_testo(frase: str, valore: int) -> None:
    """La luminosità deve essere scritta nella frase: un numero inventato non si esegue."""
    if valore not in {int(n) for n in re.findall(r"\d{1,3}", frase)}:
        raise AzioneError(f"{valore}% non è nella frase: non eseguo")


def _stanza(app: App, args: dict[str, Any]) -> Stanza | None:
    """La stanza detta dal modello (None = tutte); errori del bridge come `AzioneError`."""
    if not app.hue.configurato:
        raise AzioneError("hue non configurato (--hue-registra)")
    try:
        return app.hue.trova(str(args.get("room", "")))
    except HueError as exc:
        raise AzioneError(str(exc)) from exc


def _frase(stanza: Stanza | None, cosa: str) -> str:
    if stanza is None:
        return f"tutte le luci {cosa}"
    avviso = " (non raggiungibili)" if stanza.luci and not stanza.raggiungibili else ""
    return f"luci {stanza.nome} {cosa}{avviso}"


def _livello(frase: str) -> int | None:
    """La luminosità chiesta nella frase ("al 50%", "al 100 per cento", "al massimo"), se c'è.

    Come il verso, la legge il dashboard dal testo: il modello, per "accendi il soggiorno al
    100%", risponde `lights_off` e perderebbe il livello.
    """
    testo = frase.lower()
    trovato = PERCENTO.search(testo)
    if trovato:
        livello = int(trovato.group(1))
        if not 1 <= livello <= 100:
            raise AzioneError("luminosità da 1 a 100")
        return livello
    return 100 if MASSIMO.search(testo) else None


def _luci(app: App, args: dict[str, Any], frase: str) -> Esito:
    """Accende o spegne le luci di una stanza (o tutte): il modello dà la stanza, il verso è del testo.

    Accendendo, un livello nella frase ("accendi il soggiorno al 100%") regola anche la luminosità.
    """
    acceso = _verso(frase)
    livello = _livello(frase) if acceso else None
    stanza = _stanza(app, args)
    try:
        app.hue.imposta(stanza, acceso, livello)
    except HueError as exc:
        raise AzioneError(str(exc)) from exc
    cosa = ("accese" if acceso else "spente") + (f" al {livello}%" if livello else "")
    return _frase(stanza, cosa), ""


def _luminosita(app: App, args: dict[str, Any], frase: str) -> Esito:
    try:
        percento = round(float(args["percent"]))
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise AzioneError("luminosità non valida") from exc
    if not 1 <= percento <= 100:
        raise AzioneError("luminosità da 1 a 100")
    _numero_nel_testo(frase, percento)
    stanza = _stanza(app, args)
    try:
        app.hue.imposta(stanza, True, percento)
    except HueError as exc:
        raise AzioneError(str(exc)) from exc
    return _frase(stanza, f"al {percento}%"), ""


def _luci_comando(app: App, args: dict[str, Any], frase: str) -> Esito:
    """Luci con argomenti espliciti: stanza, acceso, percentuale, colore, temperatura, variazione.

    Viene dall'interprete di frasi o da una azione personalizzata, non dal modello: gli argomenti
    sono già quelli voluti e non si rileggono dal testo. Cambiare luminosità o colore accende.
    """
    stanza_detta = str(args.get("room", "")).strip()
    if not stanza_detta:
        raise AzioneError("di quale stanza?")      # "" non vale "tutte": mai accendere casa per un equivoco
    colore, temp = args.get("color"), args.get("temp")
    if colore is not None and colore not in COLORI:
        raise AzioneError(f"colore sconosciuto: {colore}")
    if temp is not None and temp not in TEMPERATURE:
        raise AzioneError(f"temperatura sconosciuta: {temp}")
    try:
        percento = None if args.get("percent") is None else round(float(args["percent"]))
        delta = None if args.get("delta") is None else round(float(args["delta"]))
    except (TypeError, ValueError, OverflowError) as exc:
        raise AzioneError("luminosità non valida") from exc
    if percento is not None and not 1 <= percento <= 100:
        raise AzioneError("luminosità da 1 a 100")
    if delta is not None and not -100 <= delta <= 100:
        raise AzioneError("variazione da −100 a 100")
    stanza = _stanza(app, {"room": stanza_detta})
    acceso = bool(args["on"]) if args.get("on") is not None else True
    if not acceso:
        percento = colore = temp = delta = None
    try:
        app.hue.imposta(stanza, acceso, percento, colore, temp, delta)
    except HueError as exc:
        raise AzioneError(str(exc)) from exc
    cosa = ["accese" if acceso else "spente"]
    if percento is not None:
        cosa.append(f"al {percento}%")
    if delta:
        cosa.append(f"{'+' if delta > 0 else '−'}{abs(delta)}%")
    if colore or temp:
        cosa.append(colore or f"luce {temp}")
    return _frase(stanza, " ".join(cosa)), ""


AZIONI: dict[str, Azione] = {
    "lights_on": _luci,
    "lights_off": _luci,
    "set_brightness": _luminosita,
    "start_timer_minutes": _timer("minutes", 60),
    "start_timer_seconds": _timer("seconds", 1),
    "start_timer": _timer("seconds", 1),
    "stop_timer": _comando_timer("cancel", "timer fermato", "timer già fermo"),
    "pause_timer": _comando_timer("pause", "timer in pausa", "il timer non sta scorrendo"),
    "resume_timer": _comando_timer("resume", "timer riparte", "il timer non è in pausa"),
    "delete_alarm": _togli_sveglia,
    "lights": _luci_comando,
    "set_alarm": _sveglia,
    "get_weather": _meteo,
    "set_weather_city": _citta_meteo,
    **{f"open_{chiave}": _apri(kind, nome) for chiave, (kind, nome) in PAGINE.items()},
}


# Funzioni che solo l'interprete di frasi (`frasi.py`) e le azioni personalizzate chiamano: il modello
# non le conosce, quindi non stanno in needle/tools.json.
SOLO_REGOLE = frozenset({"start_timer", "stop_timer", "pause_timer", "resume_timer", "delete_alarm",
                         "lights", "set_weather_city"})


def categoria(nome: str) -> str:
    """Quanto costa sbagliare, e quindi quale soglia di confidenza serve.

    `pagina`: apre soltanto una pagina, sbagliare costa un tocco. `luci`: cambia lo stato di
    casa ma si annulla con un comando, ed è protetto dai controlli sul verbo e sul numero.
    `stato`: timer e sveglia, dove un errore passa inosservato.
    """
    if nome.startswith("open_") or nome in ("get_weather", "set_weather_city"):
        return "pagina"
    if nome in ("lights_on", "lights_off", "set_brightness", "lights"):
        return "luci"
    return "stato"


def esegui(app: App, nome: str, args: dict[str, Any], naviga: bool = True, frase: str = "") -> str:
    """Esegue una funzione di Needle e dice cosa è successo; gli errori tornano come testo.

    `frase` è quella detta dall'utente. Con `naviga` si apre la pagina interessata, altrimenti si
    resta dove si era (anche se per l'azione è stato necessario creare una pagina).
    """
    azione = AZIONI.get(nome)
    if azione is None:
        return f"funzione non prevista: {nome}"
    corrente = app.page
    try:
        testo, kind = azione(app, args, frase)
    except AzioneError as exc:
        app.restore_page(corrente)
        return f"errore: {exc}"
    if naviga and kind:
        app.open_kind(kind)
    else:
        app.restore_page(corrente)
    return testo
