"""Funzioni che Needle può far eseguire al dashboard: `needle/tools.json` le dichiara, qui si eseguono.

Il modello propone, il dashboard decide: ogni azione controlla gli argomenti (minuti e orari
entro limiti, pagine da una lista fissa) e non fa mai nulla di irreversibile (niente spegnimento).
Si eseguono nel ciclo principale (`App.step`), mai nel thread della richiesta.

Le funzioni sono pensate per un modello da 35 MB, che copia il numero dalla frase senza
convertire le unità e capisce poco l'italiano: una funzione per unità di tempo
(`start_timer_minutes`, `start_timer_seconds`) e una senza argomenti per ogni pagina (`open_*`)
danno risposte molto più affidabili di un'unica `start_timer(minutes)` e di `show_page(page)`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from .widgets.alarm import AlarmWidget
from .widgets.timer import TimerWidget

if TYPE_CHECKING:
    from .app import App, Page

MAX_TIMER_MIN = 180
# Funzione open_<nome> → (tipo di widget, nome mostrato).
PAGINE = {"home": ("clock", "home"), "weather": ("weather", "meteo"), "timer": ("timer", "timer"),
          "alarm": ("alarm", "sveglia"), "system": ("system", "sistema"),
          "settings": ("new", "impostazioni")}

Esito = tuple[str, str]  # (frase per lo schermo, tipo di pagina da aprire, "" se nessuna)
Azione = Callable[["App", dict[str, Any]], Esito]


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
    def azione(app: App, args: dict[str, Any]) -> Esito:
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


def _sveglia(app: App, args: dict[str, Any]) -> Esito:
    try:
        hh, mm = (int(p) for p in str(args["time"]).split(":"))
    except (KeyError, ValueError) as exc:
        raise AzioneError("orario non valido (serve HH:MM)") from exc
    if not (0 <= hh < 24 and 0 <= mm < 60):   # prima di creare la pagina: un rifiuto non lascia tracce
        raise AzioneError("orario non valido (serve HH:MM)")
    widget = _pagina(app, "alarm").widget
    assert isinstance(widget, AlarmWidget)
    try:
        widget.add_alarm(hh, mm)
    except ValueError as exc:   # per esempio troppe sveglie
        raise AzioneError(str(exc)) from exc
    app.save_alarms(widget)
    return f"sveglia {hh:02d}:{mm:02d} ogni giorno", "alarm"


def _apri(kind: str, nome: str) -> Azione:
    """Apre una pagina già presente (non se ne aggiungono per un "apri")."""
    def azione(app: App, args: dict[str, Any]) -> Esito:
        if app.find_page(kind) is None:
            raise AzioneError(f"pagina {nome} non presente")
        return f"apro {nome}", kind
    return azione


def _meteo(app: App, args: dict[str, Any]) -> Esito:
    _pagina(app, "weather")
    # il meteo è quello del luogo del dashboard: per un'altra città si dice, non si finge
    return ("apro il meteo (luogo del dashboard)" if args.get("city") else "apro il meteo"), "weather"


AZIONI: dict[str, Azione] = {
    "start_timer_minutes": _timer("minutes", 60),
    "start_timer_seconds": _timer("seconds", 1),
    "set_alarm": _sveglia,
    "get_weather": _meteo,
    **{f"open_{chiave}": _apri(kind, nome) for chiave, (kind, nome) in PAGINE.items()},
}


def solo_pagina(nome: str) -> bool:
    """True per le funzioni che aprono soltanto una pagina: sbagliare costa un tocco, quindi
    bastano una confidenza più bassa (`needle.soglia_pagine`) e nessuna conferma."""
    return nome.startswith("open_") or nome == "get_weather"


def esegui(app: App, nome: str, args: dict[str, Any], naviga: bool = True) -> str:
    """Esegue una funzione di Needle e dice cosa è successo; gli errori tornano come testo.

    Con `naviga` si apre la pagina interessata, altrimenti si resta dove si era (anche se per
    l'azione è stato necessario creare una pagina).
    """
    azione = AZIONI.get(nome)
    if azione is None:
        return f"funzione non prevista: {nome}"
    corrente = app.page
    try:
        frase, kind = azione(app, args)
    except AzioneError as exc:
        app.restore_page(corrente)
        return f"errore: {exc}"
    if naviga and kind:
        app.open_kind(kind)
    else:
        app.restore_page(corrente)
    return frase
