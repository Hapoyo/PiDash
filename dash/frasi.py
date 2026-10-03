"""Interprete delle frasi per Needle: timer, sveglie e luci capiti dal codice, senza il modello.

Il modello da 35 MB copia male i numeri e conosce poco l'italiano, quindi per le richieste che si
possono leggere con regole sicure (durate, orari, giorni, stanze, colori) decide il dashboard:
è istantaneo e ripetibile. Quello che non si riconosce con certezza torna `None` e la frase va
al modello come prima. Qui non si esegue nulla: `interpreta` restituisce le chiamate
`(funzione, argomenti)` da dare a `azioni.esegui`, le stesse che produrrebbe il modello.

Azioni personalizzate (`needle.azioni`): voci scritte in configurazione che uniscono timer,
sveglia, luci e pagina sotto una o più frasi chiave ("pasta", "buonanotte", "cinema").
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable

from .hue import COLORI, TEMPERATURE

GIORNI = ("lunedi", "martedi", "mercoledi", "giovedi", "venerdi", "sabato", "domenica")
TUTTI = frozenset(range(7))
FERIALI = frozenset(range(5))
WEEKEND = frozenset({5, 6})
DELTA_PREDEFINITO = 20          # alza/abbassa senza dire di quanto: punti percentuali
MAX_AZIONI = 30

Chiamata = tuple[str, dict[str, Any]]
Stanze = Callable[[], "list[str] | None"]

UNITA = {"zero": 0, "un": 1, "uno": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5,
         "sei": 6, "sette": 7, "otto": 8, "nove": 9, "dieci": 10, "undici": 11, "dodici": 12,
         "tredici": 13, "quattordici": 14, "quindici": 15, "sedici": 16, "diciassette": 17,
         "diciotto": 18, "diciannove": 19}
DECINE = {"venti": 20, "trenta": 30, "quaranta": 40, "cinquanta": 50, "sessanta": 60,
          "settanta": 70, "ottanta": 80, "novanta": 90}
ORE = {"ora", "ore", "h"}
MINUTI = {"minuto", "minuti", "min", "m"}
SECONDI = {"secondo", "secondi", "sec", "s"}
SECONDI_UNITA = {**dict.fromkeys(ORE, 3600), **dict.fromkeys(MINUTI, 60),
                 **dict.fromkeys(SECONDI, 1)}
STOP_LUCI = frozenset({
    "accendi", "accendere", "accendimi", "attiva", "spegni", "spegnere", "spegnimi", "disattiva",
    "oscura", "illumina", "alza", "abbassa", "aumenta", "riduci", "attenua", "dimmer", "imposta",
    "metti", "mettimi", "porta", "luce", "luci", "lampada", "lampade", "il", "lo", "la", "le", "i",
    "gli", "l", "di", "del", "della", "dello", "dei", "delle", "in", "nel", "nella", "a", "al",
    "alla", "allo", "ai", "alle", "per", "favore", "piu", "meno", "luminosa", "luminosita",
    "intensita", "percento", "massimo", "massima", "minimo", "minima", "meta", "colore", "tutte",
    "tutto", "tutti", "casa", "ovunque", "un", "po", "poco", "su", "giu", "stanza", "e", "calda",
    "caldo", "fredda", "freddo", "naturale", "neutra", "neutro", "bianca", "bianco", "color"})

# Radici delle parole italiane dei colori → chiave di `hue.COLORI` o `hue.TEMPERATURE`.
COLORE_RADICI = (("ross", "rosso"), ("arancio", "arancione"), ("giall", "giallo"),
                 ("verd", "verde"), ("azzurr", "azzurro"), ("celest", "azzurro"),
                 ("blu", "blu"), ("viol", "viola"), ("lill", "viola"), ("rosa", "rosa"))
TEMPERATURA_PAROLE = {"calda": "calda", "caldo": "calda", "fredda": "fredda", "freddo": "fredda",
                      "naturale": "naturale", "neutra": "naturale", "neutro": "naturale",
                      "bianca": "bianca", "bianco": "bianca"}


def normalizza(frase: str) -> str:
    """Minuscole senza accenni: "Svegliami alle 7 e mezza!" → "svegliami alle 7 e mezza "."""
    base = unicodedata.normalize("NFKD", frase).encode("ascii", "ignore").decode("ascii").lower()
    base = base.replace("%", " percento ").replace("'", " ")
    base = re.sub(r"\bper\s*cento\b", " percento ", base)
    return base


def parole(frase: str) -> list[str]:
    """Parole e numeri della frase, con gli orari "7:30" / "7.30" interi."""
    return re.findall(r"\d{1,2}[:.]\d{2}|\d+|[a-z]+", normalizza(frase))


def numero(parola: str) -> int | None:
    """Numero scritto in cifre o in lettere (fino a 999): "venticinque" → 25, "ventotto" → 28."""
    if parola.isdigit():
        return int(parola)
    if parola in UNITA:
        return UNITA[parola]
    if parola in DECINE:
        return DECINE[parola]
    cento = re.fullmatch(r"(?:(due|tre|quattro|cinque|sei|sette|otto|nove))?cent(?:o)?(.*)", parola)
    if cento:
        resto = numero(cento.group(2)) if cento.group(2) else 0
        if resto is None or resto >= 100:
            return None
        return (UNITA[cento.group(1)] if cento.group(1) else 1) * 100 + resto
    for decina, valore in DECINE.items():
        for forma in (decina, decina[:-1]):          # ventuno, ventotto: cade la vocale
            if parola.startswith(forma) and parola != forma:
                unita = UNITA.get(parola[len(forma):])
                if unita is not None and 1 <= unita <= 9 and (
                        forma == decina or parola[len(forma):][0] in "uo"):
                    return valore + unita
    return None


# --- durate ----------------------------------------------------------------------------
def durata(p: list[str]) -> int | None:
    """Secondi di una durata detta in qualsiasi modo; None se non ce n'è una chiara.

    "5 minuti", "un'ora e mezza", "1 ora e 30", "mezz'ora", "un quarto d'ora", "due minuti e
    mezzo", "1h 15min", "90 secondi", "un minuto e 30 secondi".
    """
    totale, trovata, i = 0, False, 0
    ultima = 0          # unità dell'ultimo termine, per "e 30" / "e mezza"
    while i < len(p):
        w = p[i]
        n = numero(w)
        # "mezz'ora", "mezzora"
        if w in ("mezz", "mezza", "mezzo", "mezzora") and (w == "mezzora" or p[i + 1:i + 2] == ["ora"]):
            totale += 1800
            trovata, ultima = True, 3600
            i += 1 if w == "mezzora" else 2
            continue
        # "(un|tre) quarto/quarti (d'ora)"
        if w in ("un", "uno", "tre") and p[i + 1:i + 2] in (["quarto"], ["quarti"]):
            k = 1 if w != "tre" else 3
            if p[i + 2:i + 4] == ["d", "ora"] or p[i + 2:i + 3] == ["dora"] or ultima == 3600:
                totale += 900 * k
                trovata, ultima = True, 3600
                i += 4 if p[i + 2:i + 4] == ["d", "ora"] else 3
                continue
        if n is not None and i + 1 < len(p) and p[i + 1] in SECONDI_UNITA:
            unita = SECONDI_UNITA[p[i + 1]]
            totale += n * unita
            trovata, ultima = True, unita
            i += 2
            continue
        if w == "e" and trovata and i + 1 < len(p):
            seguente = p[i + 1]
            if seguente in ("mezza", "mezzo") and ultima in (3600, 60):
                totale += ultima // 2
                i += 2
                continue
            if seguente in ("un", "uno") and p[i + 2:i + 3] == ["quarto"] and ultima == 3600:
                totale += 900
                i += 3
                continue
            m = numero(seguente)
            if m is not None and ultima in (3600, 60) and not (
                    i + 2 < len(p) and p[i + 2] in SECONDI_UNITA):
                piccola = 60 if ultima == 3600 else 1   # "1 ora e 30" = 30 minuti
                totale += m * piccola
                ultima = piccola
                i += 2
                continue
        i += 1
    return totale if trovata and totale > 0 else None


def durata_nuda(p: list[str]) -> int | None:
    """"timer 5": un numero senza unità vale minuti (solo dopo la parola timer)."""
    if "timer" in p:
        for w in p[p.index("timer") + 1:]:
            n = numero(w)
            if n is not None and 0 < n < 1000:
                return n * 60
    return None


# --- orari e giorni --------------------------------------------------------------------
def orario(p: list[str]) -> tuple[int, int] | None:
    """(ore, minuti) di un orario detto in qualsiasi modo; None se non c'è.

    "7:30", "alle 7 e mezza", "alle sette e un quarto", "alle 8 meno un quarto", "alle 7 e 15",
    "all'una", "mezzanotte", "mezzogiorno"; "di sera" / "del pomeriggio" porta alle ore 12–23.
    """
    sera = any(w in ("sera", "stasera", "pomeriggio") for w in p)
    notte = "notte" in p
    if "mezzanotte" in p:
        return 0, 0
    if "mezzogiorno" in p:
        return 12, 0
    for i, w in enumerate(p):
        if re.fullmatch(r"\d{1,2}[:.]\d{2}", w):
            hh, mm = (int(x) for x in re.split(r"[:.]", w))
        elif w in ("alle", "delle", "ore", "all", "le") and i + 1 < len(p) and (
                numero(p[i + 1]) is not None and numero(p[i + 1]) < 24):   # type: ignore[operator]
            hh, mm = numero(p[i + 1]) or 0, 0
            resto = p[i + 2:]
            if resto[:1] == ["e"] and resto[1:2] in (["mezza"], ["mezzo"]):
                mm = 30
            elif resto[:1] == ["e"] and resto[1:3] in (["un", "quarto"], ["uno", "quarto"]):
                mm = 15
            elif resto[:1] == ["e"] and resto[1:3] == ["tre", "quarti"]:
                mm = 45
            elif resto[:1] == ["e"] and resto[1:2] and numero(resto[1]) is not None \
                    and resto[2:3] not in (["ore"], ["ora"], ["minuti"], ["minuto"]):
                mm = numero(resto[1]) or 0
            elif resto[:1] == ["meno"]:
                if resto[1:3] in (["un", "quarto"], ["uno", "quarto"]):
                    tolti = 15
                elif resto[1:2] and numero(resto[1]) is not None:
                    tolti = numero(resto[1]) or 0
                else:
                    tolti = 0
                if tolti:
                    hh, mm = (hh - 1) % 24, 60 - tolti
        else:
            continue
        if not (0 <= hh < 24 and 0 <= mm < 60):
            return None
        if (sera and 1 <= hh <= 11) or (notte and 8 <= hh <= 11):
            hh += 12
        return hh, mm
    return None


def giorni(p: list[str]) -> frozenset[int] | None:
    """Giorni della settimana detti nella frase (0 = lunedì); None se non se ne parla."""
    if "feriali" in p or "lavorativi" in p or "feriale" in p:
        return FERIALI
    if "weekend" in p or ("fine" in p and "settimana" in p):
        return WEEKEND
    if "giorni" in p and ("tutti" in p or "ogni" in p) or "ogni" in p and "giorno" in p:
        return TUTTI
    trovati = [GIORNI.index(w) for w in p if w in GIORNI]
    if not trovati:
        return None
    if "dal" in p and "al" in p and len(trovati) == 2:        # "dal lunedì al venerdì"
        a, b = trovati
        return frozenset((a + k) % 7 for k in range((b - a) % 7 + 1))
    return frozenset(trovati)


# --- luci ------------------------------------------------------------------------------
def _percentuale(p: list[str]) -> int | None:
    """Luminosità dichiarata: "al 50%", "al cinquanta per cento", "metà", "al massimo"."""
    for i, w in enumerate(p):
        if w == "percento" and i > 0:
            n = numero(p[i - 1])
            if n is not None:
                return n
    for i, w in enumerate(p[:-1]):
        n = numero(p[i + 1])
        if w in ("al", "a", "su") and n is not None and 1 <= n <= 100 and p[i + 1].isdigit():
            return n                                # "luce soggiorno al 50"
    if "meta" in p:
        return 50
    if "massimo" in p or "massima" in p:
        return 100
    if "minimo" in p or "minima" in p:
        return 1
    return None


def _colore(p: list[str]) -> tuple[str | None, str | None]:
    """(colore, temperatura) nominati nella frase."""
    for w in p:
        for radice, chiave in COLORE_RADICI:
            if (w == radice) if radice == "rosa" else w.startswith(radice):
                return chiave, None
    for w in p:
        if w in TEMPERATURA_PAROLE:
            return None, TEMPERATURA_PAROLE[w]
    return None, None


def _stanza(p: list[str], stanze: Stanze | None) -> tuple[str, bool]:
    """(stanza nominata, certa): "tutte" per tutta la casa, "" se non c'è o non si capisce.

    Certa se è tra le stanze del bridge; senza bridge raggiungibile resta il testo che avanza,
    e sarà l'azione a dire cosa non va.
    """
    if any(w in ("tutte", "tutto", "tutti", "ovunque", "casa") for w in p):
        return "tutte", True
    elenco = stanze() if stanze is not None else None
    if elenco:
        migliore, lunghezza = "", 0
        for nome in elenco:
            nomi = [w for w in parole(nome) if w not in STOP_LUCI]
            if nomi and set(nomi) <= set(p) and len(nomi) > lunghezza:
                migliore, lunghezza = nome, len(nomi)
        if migliore:
            return migliore, True
    # nessuna stanza riconosciuta (o bridge irraggiungibile): resta il testo, lo dirà l'azione
    return " ".join(w for w in p if w not in STOP_LUCI and not w.isdigit()), False


def luci(p: list[str], stanze: Stanze | None) -> list[Chiamata] | None:
    """Comando per le luci: accendi/spegni, luminosità, alza/abbassa, colore, temperatura."""
    if any(w in ("non", "senza", "mai") for w in p):
        return None                              # una negazione la gestisce il controllo del modello
    acceso: bool | None = None
    if any(w.startswith(("accend", "attiv", "illumin")) for w in p):
        acceso = True
    if any(w.startswith(("spegn", "disattiv", "oscur")) for w in p):
        acceso = False if acceso is None else None
        if acceso is None:
            return None                          # verbi opposti insieme
    colore, temperatura = _colore(p)
    percento = _percentuale(p)
    delta: int | None = None
    relativo = any(w in ("alza", "aumenta", "abbassa", "riduci", "attenua", "dimmer") for w in p) \
        or ("piu" in p or "meno" in p) and any(w.startswith("luminos") for w in p)
    if relativo and percento is not None and ("di" in p or "del" in p):
        delta, percento = percento, None             # "alza di 30 percento"
    elif relativo and percento is None:
        delta = DELTA_PREDEFINITO                    # "alza la luce"
    if delta is not None and any(
            w in ("abbassa", "riduci", "attenua", "dimmer", "meno", "giu") for w in p):
        delta = -delta
    if acceso is None and colore is None and temperatura is None and percento is None \
            and delta is None:
        return None
    stanza, certa = _stanza(p, stanze)
    if acceso is None and not (certa or any(w in ("luce", "luci", "lampada", "lampade") for w in p)):
        return None                                  # "alza il volume" non è una luce
    args: dict[str, Any] = {"room": stanza}
    if acceso is not None:
        args["on"] = acceso
    for chiave, valore in (("percent", percento), ("color", colore), ("temp", temperatura),
                           ("delta", delta)):
        if valore is not None:
            args[chiave] = valore
    if acceso is False:                           # "spegni" cancella ogni altro effetto
        args = {"room": args["room"], "on": False}
    return [("lights", args)]


# --- meteo di un'altra città -----------------------------------------------------------
METEO_CITTA = re.compile(r"^\W*(?:il\s+)?meteo\s+(?:(?:a|ad|di|per|in|su|del|della|di)\s+)?(.+?)\W*$",
                         re.IGNORECASE)
CITTA_QUI = frozenset({"qui", "locale", "casa", "dashboard", "posizione", "attuale", "mio", "mia"})
NON_CITTA = frozenset({"oggi", "domani", "adesso", "ora", "dopo", "stasera", "stamattina",
                       "previsioni", "vento", "mare", "pioggia", "temperatura", "tempo"})
CITTA_MAX = 60


def meteo(frase: str) -> list[Chiamata] | None:
    """"Meteo Roma", `meteo "New York"`, "meteo a Forlì": cambia la città; "meteo qui" torna al luogo.

    Il nome resta com'è stato scritto (accenti compresi) per il geocoding. "meteo oggi" e simili
    non sono città: vanno al modello come prima.
    """
    trovato = METEO_CITTA.match(frase.strip())
    if not trovato:
        return None
    citta = re.sub(r"[\"“”«»'‘’]", " ", trovato.group(1))
    citta = " ".join(citta.split())
    p = parole(citta)
    if not p or len(citta) > CITTA_MAX or len(p) > 5:
        return None
    if all(w in CITTA_QUI or w in ("a", "di", "da", "il", "mio", "mia") for w in p):
        return [("set_weather_city", {"city": ""})]
    if p[0] in NON_CITTA:
        return None
    return [("set_weather_city", {"city": citta})]


# --- timer e sveglie -------------------------------------------------------------------
def _verbi(p: list[str], radici: tuple[str, ...]) -> bool:
    return any(w.startswith(radici) for w in p)


def timer(p: list[str]) -> list[Chiamata] | None:
    if _verbi(p, ("ferm", "annull", "cancell", "elimin", "interromp", "stoppa", "stop")):
        return [("stop_timer", {})]
    if _verbi(p, ("paus", "sospend")):
        return [("pause_timer", {})]
    if _verbi(p, ("riprend", "riavvi", "continu")):
        return [("resume_timer", {})]
    secondi = durata(p) or durata_nuda(p)
    if secondi is None:
        return None
    return [("start_timer", {"seconds": secondi})]


def sveglia(p: list[str]) -> list[Chiamata] | None:
    ora = orario(p)
    if _verbi(p, ("cancell", "elimin", "togli", "tolg", "rimuov", "annull")):
        if ora:
            return [("delete_alarm", {"time": f"{ora[0]:02d}:{ora[1]:02d}"})]
        # senza orario si cancellano tutte solo se la frase lo dice: mai per un equivoco
        return [("delete_alarm", {})] if any(w in ("tutte", "tutti", "sveglie") for w in p) else None
    if ora is None:
        return None
    args: dict[str, Any] = {"time": f"{ora[0]:02d}:{ora[1]:02d}"}
    quali = giorni(p)
    if quali is not None and quali != TUTTI:
        args["days"] = sorted(quali)
    return [("set_alarm", args)]


# --- azioni personalizzate -------------------------------------------------------------
def azione_chiamate(voce: dict[str, Any]) -> list[Chiamata]:
    """Le chiamate di una voce di `needle.azioni` (già validata da `config`)."""
    out: list[Chiamata] = []
    t = voce.get("timer")
    if t:
        out.append(("start_timer", {"seconds": int(t.get("ore", 0)) * 3600
                                    + int(t.get("minuti", 0)) * 60 + int(t.get("secondi", 0))}))
    if voce.get("sveglia"):
        args: dict[str, Any] = {"time": voce["sveglia"]}
        if voce.get("giorni"):
            args["days"] = sorted(voce["giorni"])
        out.append(("set_alarm", args))
    for luce in voce.get("luci") or []:
        args = {"room": luce.get("stanza", "tutte")}
        for chiave, nome in (("acceso", "on"), ("percentuale", "percent"), ("colore", "color"),
                             ("temperatura", "temp")):
            if chiave in luce:
                args[nome] = luce[chiave]
        out.append(("lights", args))
    if voce.get("pagina"):
        out.append((f"open_{voce['pagina']}", {}))
    return out


def personalizzata(p: list[str], voci: list[dict[str, Any]]) -> list[Chiamata] | None:
    """La voce di `needle.azioni` la cui frase chiave compare nella frase (vince la più lunga)."""
    testo = " " + " ".join(p) + " "
    migliore: tuple[int, dict[str, Any]] | None = None
    for voce in voci:
        for chiave in voce.get("frasi") or []:
            k = " ".join(parole(str(chiave)))
            if k and f" {k} " in testo and (migliore is None or len(k) > migliore[0]):
                migliore = (len(k), voce)
    return azione_chiamate(migliore[1]) if migliore else None


def interpreta(frase: str, voci: list[dict[str, Any]] | None = None,
               stanze: Stanze | None = None) -> list[Chiamata] | None:
    """Le chiamate che la frase chiede, o None se serve il modello.

    Ordine: azioni personalizzate, poi timer, sveglie, luci. Una frase con sveglia o timer che
    non si capisce non passa alle luci: "spegni la sveglia" non spegne una stanza.
    """
    p = parole(frase)
    if not p:
        return None
    if voci:
        chiamate = personalizzata(p, voci)
        if chiamate:
            return chiamate
    if any(w in ("sveglia", "sveglie", "svegliami", "svegliare", "svegliarmi") for w in p):
        return sveglia(p)
    if "timer" in p or _verbi(p, ("avvisami", "ricordami", "avvertimi")) or "countdown" in p:
        return timer(p)
    if "cronometro" in p:
        return None
    if p[0] == "meteo" or p[:2] == ["il", "meteo"]:
        return meteo(frase)
    return luci(p, stanze)


__all__ = ["COLORI", "TEMPERATURE", "azione_chiamate", "durata", "giorni", "interpreta", "luci",
           "numero", "orario", "parole", "personalizzata"]
