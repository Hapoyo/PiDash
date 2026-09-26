# pi-dash — CLAUDE.md

Versione 0.5.0 · 2026-09-27

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
dash/main.py           riga di comando: configurazione, schermo, ingressi, avvio
dash/app.py            App: pagine dello schedario, eventi, ciclo (`step`, `run`)
dash/preview.py        anteprime del README: PNG per pagina e GIF animata
dash/config.py         default + validazione (ConfigError)
dash/motion.py         tempi delle animazioni: livelli, curve, avvio, scansione, decodifica
dash/render/           tutto il disegno
  theme.py             colori, font, `fit`, cache dei testi
  canvas.py            Canvas: primitive dello stile + registro di numeri ed effetti
  folders.py           schedario: geometria delle linguette (disegno e tocco), cartelle
  pages/               una `draw(cv, box, app, now)` per tipo di pagina + registro `PAGES`
  effects.py           animazioni sopra la base, sequenza di avvio, riquadro di allarme
  renderer.py          CyberRenderer: `render` (pagina base) e `compose` (fotogramma animato)
dash/layout.py         Box e nomi di giorni/mesi
dash/location.py       posizione condivisa: "ip" (IP pubblico), "city" (geocoding), "fixed"
dash/astro.py          alba/tramonto calcolati in locale (NOAA semplificato, ±1–2 min)
dash/sysinfo.py        CPU/RAM/disco/temperatura/uptime/IP da /proc e /sys
dash/inputs.py         Event, tastiera (stdin), pulsanti GPIO, touch evdev, cicalino
dash/display/          base.py, sim.py (PNG + pagina web), fb.py (/dev/fbN)
dash/widgets/          dati e stato: clock, weather, timer, alarm, system, new (nessun disegno)
docs/                  installazione.md (guida), hardware.md (pin, overlay, SPI), decisioni.md
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
  e `docs/img/animazione.gif` (dati demo, posizione fissa, istante 24/09/2026 07:42, nessuna rete).
  Rigenerarle quando cambia il disegno.
- Animazioni: `--motion off|eventi|pieno` sovrascrive `motion.livello`.
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
- I widget forniscono **solo dati e stato**: niente disegno. Tutto il disegno sta in `dash/render/`.
- Nuovo widget: sottoclasse di `Widget`, registrarlo in `widgets/__init__.py` (`WIDGET_NAMES` +
  `WidgetFactory.make`), un modulo `render/pages/<nome>.py` con `draw(cv, box, app, now)` e la
  voce in `PAGES`, l'etichetta in `widgets/new.py` (`ETICHETTE`) e un test.
- Le pagine disegnano solo con i metodi di `Canvas` (`cv.text`, `cv.label`, `cv.big`, `cv.panel`,
  `cv.ring`, `cv.progress`, `cv.rows`, `cv.graph`, `cv.rect`); `cv.d` (ImageDraw) solo per linee
  ed ellissi senza equivalente. Un elemento che serve a due pagine va in `Canvas`.
- Le pagine leggono **solo** `app.page.widget`, mai `app.widgets[...]`: dello stesso tipo possono
  esserci più pagine, ognuna con il proprio stato.
- Testo a video minuscolo, ma `cv.label`/`cv.rows` accettano `lower=False` dove il maiuscolo
  conta (kB/s, °C).
- Misure: solo dalla griglia `GRID` in `render/theme.py` (pixel sullo schermo 480×320, scala
  `u = min(w/480, h/320)`): `cv.margin`, `cv.gap`, `cv.pad`, `cv.radius`, `cv.line`, `cv.stroke`,
  `cv.px(n)`. Niente numeri magici nelle pagine. Testi: `cv.label` (12 px) e `small=True` (11 px);
  numeri grandi con `cv.big`/`cv.panel` adattati al riquadro, stessa serie con lo stesso `ref`
  ("7%" e "100%" uguali). Allineamento: etichetta, numero e dettaglio a sinistra nei pannelli.
- Ogni widget implementa `state_key()`: se non cambia, la pagina base non viene ridisegnata.
- Animazioni: `motion.py` non disegna e non legge l'orologio (riceve `t`); durante `render` il
  Canvas registra i numeri (`cv.big`/`cv.panel` con `slot=`) e gli effetti (`cv.add_fx`),
  `compose` li anima sopra la base. Un effetto nuovo: ramo in `effects.draw_fx` + `cv.add_fx`.
- Testo sempre con `cv.text` (cache delle maschere): mai `ImageDraw.text` diretto nelle pagine.
- Refactor del disegno: le immagini devono restare identiche. Confrontare le impronte SHA-1 delle
  pagine (più risoluzioni) e dei fotogrammi della GIF prima e dopo.
- Commit: uno per intervento, messaggi in italiano all'imperativo.
- Il Pi si aggiorna da `main`: ciò che arriva su `main` deve passare `python -m unittest`
  (altrimenti `aggiorna.sh` rifiuta l'aggiornamento e torna indietro).
- Nuove voci di configurazione: default in `DEFAULTS` di `config.py`, così i `config.local.json`
  esistenti restano validi. Mai rendere obbligatoria una voce senza default.
- I test non devono dipendere dal `config.local.json` della macchina: `aggiorna.sh` li esegue sul
  Pi, dove quel file esiste ed è diverso. Per provare `config.json` copiarlo in una cartella vuota.
- I test non devono dipendere dall'orologio vero: `App.step(now, t, animate=...)` con istanti
  fissi. Un test che fallisce a caso sul Pi blocca gli aggiornamenti.

## 5. Vincoli hardware
Pin, overlay `piscreen`, alimentazione, calibrazione del touch: [docs/hardware.md](docs/hardware.md).
Leggerlo prima di toccare `display/fb.py` o `inputs.py`.

## 6. Decisioni
Scelte prese e motivi (schedario, meteo, posizione, animazioni, configurazione, aggiornamento):
[docs/decisioni.md](docs/decisioni.md). Leggerlo prima di cambiare il comportamento di una parte.

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
