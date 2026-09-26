# pi-dash — CLAUDE.md

Versione 0.3.1 · 2026-09-26

## 1. Scopo
Dashboard da tavolo per Raspberry Pi 3 Model B con schermo SPI 3,5" 480×320 (ILI9486 + touch
XPT2046): orologio, meteo e vento in nodi, timer di partenza regata, sveglia, statistiche del
sistema. Schedario componibile: le pagine si aggiungono e si tolgono dalla scheda "+".
Unico stile: pannelli arrotondati a colori su fondo scuro, numeri in Space Grotesk,
microetichette in Space Mono.

## 2. Struttura
```
README.md              presentazione per GitHub (anteprime in docs/img/NN-pagina.png)
config.json            configurazione del progetto: display, posizione, pagine, sveglie, touch
config.local.json      impostazioni del singolo Pi, fuori da Git, fuse sopra config.json
dash/main.py           loop, pagine, eventi, CLI
dash/config.py         default + validazione (ConfigError)
dash/cyber.py          tutto il disegno: schedario e una funzione per pagina (immagini RGB)
dash/layout.py         Box e nomi di giorni/mesi
dash/location.py       posizione condivisa: "ip" (IP pubblico), "city" (geocoding), "fixed"
dash/astro.py          alba/tramonto calcolati in locale (NOAA semplificato, ±1–2 min)
dash/sysinfo.py        CPU/RAM/disco/temperatura/uptime/IP da /proc e /sys
dash/inputs.py         Event, tastiera (stdin), pulsanti GPIO, touch evdev, cicalino
dash/display/          base.py, sim.py (PNG + pagina web), fb.py (/dev/fbN)
dash/widgets/          dati e stato: clock, weather, timer, alarm, system, new (nessun disegno)
docs/                  installazione.md (guida passo passo), hardware.md (pin, overlay, alimentazione)
fonts/                 Space Grotesk, Space Mono (OFL) + licenze
scripts/aggiorna.sh    aggiornamento sul Pi: pull, dipendenze, test, riavvio, rollback
scripts/installa-servizio.sh  installa systemd/pi-dash.service con utente e cartella reali
systemd/pi-dash.service  avvio automatico (modello: User=pi, /home/pi/pi-dash)
tests/                 unittest
```

## 3. Comandi
- Setup sviluppo: `python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt`
- Simulatore: `python -m dash --demo --web 8080 --driver sim` → `http://localhost:8080`
- Un fotogramma: `python -m dash --once --demo --driver sim --page 2` → `out/frame.png`
- Anteprime README: `TZ=Europe/Rome python -m dash --screenshots docs/img` → `docs/img/NN-pagina.png`
  (dati demo, posizione fissa, istante 24/09/2026 07:42, nessuna rete). Rigenerarle quando cambia il disegno.
- Repository: https://github.com/Hapoyo/PiDash
- Test: `python -m unittest -v`
- Installazione sul Raspberry: [docs/installazione.md](docs/installazione.md)
- Aggiornare il Pi: `~/pi-dash/scripts/aggiorna.sh [--no-test]` (segue il ramo in uso, di norma `main`)
- Servizio: `scripts/installa-servizio.sh` (mai `sed -i` sul file in Git)
- Calibrazione tocco: `.venv/bin/python -m dash --touch-debug`
- Comandi: N pagina seguente · A azione (avvia/ferma timer, spegne sveglia) · B indietro/preset
- Tocco: linguetta → apre quella cartella; contenuto → azione del widget della pagina

## 4. Convenzioni
- Python ≥ 3.11, type hints, docstring brevi, errori espliciti (nessun `except:` nudo).
- Sola dipendenza obbligatoria: Pillow. gpiozero solo sul Pi, importato in modo lazy.
- Testi a video in italiano minuscolo; vento in nodi (kn); temperature in °C; orari 24 h.
- I widget forniscono **solo dati e stato**: niente disegno. Tutto il disegno sta in `cyber.py`.
- Nuovo widget: sottoclasse di `Widget`, registrarlo in `widgets/__init__.py` (`WIDGET_NAMES` +
  `WidgetFactory.make`), aggiungere il metodo `_<nome>` in `cyber.py` e la voce nella tabella di
  `CyberRenderer.render`, l'etichetta in `widgets/new.py` (`ETICHETTE`) e un test.
- Le pagine leggono **solo** `app.page.widget`, mai `app.widgets[...]`: dello stesso tipo possono
  esserci più pagine, ognuna con il proprio stato.
- Testo a video minuscolo, ma `_micro`/`_rows` accettano `lower=False` dove il maiuscolo conta
  (kB/s, °C).
- Misure: tutto scala con `u = min(w/960, h/540)`; i numeri della stessa serie si dimensionano su
  una stringa di riferimento (`_panel(ref=...)`), così "7%" e "100%" restano uguali.
- Ogni widget implementa `state_key()`: se non cambia, il fotogramma non viene ridisegnato.
- Commit: uno per intervento, messaggi in italiano all'imperativo.
- Il Pi si aggiorna da `main`: ciò che arriva su `main` deve passare `python -m unittest`
  (altrimenti `aggiorna.sh` rifiuta l'aggiornamento e torna indietro).
- Nuove voci di configurazione: default in `DEFAULTS` di `config.py`, così i `config.local.json`
  esistenti restano validi. Mai rendere obbligatoria una voce senza default.
- I test non devono dipendere dal `config.local.json` della macchina: `aggiorna.sh` li esegue sul
  Pi, dove quel file esiste ed è diverso. Per provare `config.json` copiarlo in una cartella vuota.

## 5. Vincoli hardware
Pin, overlay `piscreen`, alimentazione, calibrazione del touch: [docs/hardware.md](docs/hardware.md).
Leggerlo prima di toccare `display/fb.py` o `inputs.py`.

## 6. Decisioni
- Schedario: una linguetta numerata per pagina. Le pagine precedenti restano in pila in alto, le
  successive in pila in basso; la cartella aperta parte dalla propria linguetta. Geometria unica in
  `CyberRenderer.layout(w, h, n, current)`, usata sia dal disegno sia dal tocco.
- Home: ora, data, luogo e coordinate, alba/tramonto, barra della giornata, settimana n:X,
  giorno X/365 (366 negli anni bisestili), tre anelli concentrici (anno arancio, mese ambra,
  settimana crema) con una sfera in testa all'arco: `ClockWidget.cycles`.
- Schedario componibile: la scheda "+" (`widgets/new.py`) elenca solo i tipi opzionali
  (`new.tipi`, di norma timer e sveglia); ogni voce fa da interruttore, quindi una sola pagina
  per tipo. `App.add_page`/`remove_page` creano il widget e salvano `pages` in
  `config.local.json`; `App.page_kinds()` dice al widget cosa è già presente. Chiave della pagina
  `tipo` o `tipo#N`, sempre libera anche dopo una rimozione (più copie restano possibili da
  configurazione). La scheda "+" resta ultima e non si può togliere.
- Meteo: bussola senza ago — riga dagli estremi arrotondati dal centro verso la direzione **da
  cui** soffia il vento (uso nautico), gradi nell'etichetta del pannello; `_panel(reserve=...)`
  libera lo spazio a destra del numero.
- Rete: byte/s da `/proc/net/dev` (tutte le schede tranne `lo`), differenza fra due campioni;
  il primo campione dopo l'avvio vale None. Storico nel widget sistema, grafico in scala sul picco.
- Meteo: Open-Meteo (nessuna chiave), `wind_speed_unit=kn`, `timezone=auto`, 2 giorni orari;
  cache in `out/weather_cache.json`, contatore di versione per il ridisegno. Fase lunare calcolata
  localmente (mese sinodico medio).
- Posizione: `location.mode` = `ip` (ipapi.co poi ip-api.com), `city` (geocoding Open-Meteo),
  `fixed`. `name/lat/lon` fanno da ripiego; cache in `out/location.json`, aggiornata ogni
  `refresh_h`. Cambio di posizione → dati meteo vecchi scartati.
- Alba/tramonto della Home: calcolo locale (funziona senza rete), nel fuso del sistema, quindi il
  Pi deve avere Europe/Rome. La pagina meteo usa i valori Open-Meteo.
- Timer: etichette per preset `timer.labels` (es. 300 s → "PARTENZA"); B cambia preset.
- Sistema: campioni ogni `system.sample_s`, storici di CPU e rete su 48 colonne a larghezza fissa.
- Driver `fb`: scrive nel framebuffer (RGB565 o XRGB8888), niente desktop; trova il pannello per
  nome del driver (ili9486…). Con `console_off` mette la console in modalità grafica (KDSETMODE,
  serve CAP_SYS_TTY_CONFIG: già nel servizio). Touch evdev senza dipendenze (`dash/inputs.py`).
- Con allarme attivo (sveglia/timer) qualsiasi tocco o il tasto A lo spegne, ovunque ci si trovi.
- Suono: cicalino su GPIO (`input.buzzer_pin`), altrimenti campanella del terminale (`input.sound`).
- Simulatore web con pulsanti virtuali per sviluppo senza hardware.
- Configurazione a due livelli: `DEFAULTS` ← `config.json` ← `config.local.json` (`_merge`
  ricorsivo sui dizionari, le liste si sostituiscono). Il Pi non modifica mai file in Git: così
  `git pull --ff-only` non trova conflitti.
- `aggiorna.sh`: file tracciati modificati → blocca (tranne config.json, spostato in
  config.local.json, e il file del servizio, ripristinato); test o config non validi → `git reset
  --hard` al commit precedente.
- Da collaudare sull'hardware: overlay e framebuffer, orientamento del touch, pulsanti GPIO, cicalino.

## 7. Glossario
- **WMO code**: codice meteo standard restituito da Open-Meteo (`weather_code`).
- **kn**: nodi (1 kn = 1852 m/h ≈ 0,514 m/s).
- **F (Beaufort)**: forza del vento 0–12, soglie in nodi in `widgets/weather.py`.
- **Rosa dei venti**: 16 quarte (N…NNW) e 8 venti (Tramontana…Maestrale).
- **Fase lunare**: 0 = luna nuova, 0,5 = piena; illuminazione in % del disco.
- **SoC**: System on Chip del Raspberry (temperatura mostrata come "temp").
- **Partenza**: sequenza di partenza di regata (conto alla rovescia di 5').
- **Framebuffer**: `/dev/fb1`, memoria dello schermo scritta direttamente, senza desktop.
- **Scheda "+"**: pagina `new`, catalogo per comporre lo schedario.
