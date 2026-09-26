# pi-dash

Versione 0.4.0 · 2026-09-26

Dashboard da tavolo per Raspberry Pi 3 Model B con schermo SPI 3,5" touch: orologio, meteo e vento
in nodi, timer di partenza regata, sveglia e statistiche del sistema.

![Animazioni: avvio, cambio pagina, numeri che si decodificano](docs/img/animazione.gif)

Le pagine sono le cartelle di uno schedario: si tocca la linguetta numerata e la cartella si apre
sotto di essa. Stesso stile ovunque — pannelli arrotondati a colori su fondo scuro, numeri in
Space Grotesk, microetichette in Space Mono — e motion graphics da computer di bordo: sequenza di
accensione, scansione al cambio pagina, cifre che si decodificano, radar e spie che vivono.

Lo schedario si compone a piacere: la scheda **+** elenca le schede opzionali — timer e sveglia —
e ogni voce fa da interruttore: le aggiunge se mancano, le toglie se ci sono. La scelta si salva
in `config.local.json` e torna al riavvio.

## 1. Pagine
| # | Pagina | In partenza | Contenuto |
|---|---|---|---|
| 001 | Home | sì | ora, data, luogo e coordinate, alba/tramonto, barra della giornata, anelli di settimana/mese/anno |
| 002 | Meteo | sì | temperatura, vento con bussola e gradi, raffiche e Beaufort, pioggia, umidità, pressione, previsione oraria, sole e luna |
| 003 | Timer | da aggiungere | conto alla rovescia con preset (5' = sequenza di partenza) |
| 004 | Sveglia | da aggiungere | prossima sveglia, stato, elenco per giorno della settimana |
| 005 | Sistema | sì | CPU, RAM, disco, storici di CPU e rete, host, IP, temperatura, uptime |
| + | Nuova scheda | sì | elenco delle schede opzionali: le aggiunge o le toglie |

### 1.1 Anteprime
| 001 · Home | 002 · Meteo |
|:---:|:---:|
| ![Home: ora, data, luogo, alba e tramonto, anelli di settimana, mese e anno](docs/img/01-home.png) | ![Meteo: temperatura, vento in nodi con bussola, pioggia, umidità, pressione, previsione oraria](docs/img/02-meteo.png) |
| **003 · Timer** | **004 · Sveglia** |
| ![Timer: conto alla rovescia di partenza con preset](docs/img/03-timer.png) | ![Sveglia: orario, stato e prossima attivazione](docs/img/04-sveglia.png) |
| **005 · Sistema** | **+ · Nuova scheda** |
| ![Sistema: CPU, RAM, disco, storici di CPU e rete, host, IP, temperatura, uptime](docs/img/05-sistema.png) | ![Nuova scheda: elenco delle schede opzionali, timer e sveglia](docs/img/06-new.png) |

Le anteprime mostrano tutte le pagine, comprese quelle da aggiungere.
Immagini a 480×320, risoluzione nativa dello schermo, generate dal codice con dati demo:
`python -m dash --screenshots docs/img` (fuori dal Pi anteporre `TZ=Europe/Rome`).

### 1.2 Animazioni
| Effetto | Dove | Livello |
|---|---|---|
| Accensione: sigla che si scrive, righe di controllo, barra di carico (2,4 s, un tocco la salta) | all'avvio | eventi |
| Scansione dall'alto con riga arancio | a ogni cambio pagina | eventi |
| Cifre che scorrono e si fermano da sinistra a destra | numeri grandi che cambiano o all'apertura della pagina | eventi |
| Due punti che lampeggiano | ora della home, timer in corsa | pieno |
| Aloni che pulsano attorno alle sfere | anelli della home | pieno |
| Radar che gira | bussola del vento | pieno |
| Cursore che percorre i grafici | storici di CPU e rete | pieno |
| Spia accanto al numero della linguetta aperta | tutte le pagine | pieno |

`motion.livello` in `config.local.json`: `"pieno"` (predefinito), `"eventi"` o `"off"`;
`motion.fps` (predefinito 8). Durante un allarme gli effetti continui si fermano.

Dati meteo: [Open-Meteo](https://open-meteo.com), senza chiave. Alba e tramonto della Home sono
calcolati in locale: funzionano anche senza rete.

## 2. Hardware
| Voce | Dato |
|---|---|
| Scheda | Raspberry Pi 3 Model B, Raspberry Pi OS Lite 64 bit |
| Schermo | "3.5inch RPi Display" 480×320, ILI9486 + touch XPT2046 (overlay `piscreen,drm`) |
| Alimentatore | 5,1 V 2,5 A |
| Opzionali | pulsanti su GPIO 5/13/19, cicalino su GPIO 26 |

Pin e vincoli: [docs/hardware.md](docs/hardware.md).

## 3. Installazione
Guida passo passo, anche per chi non ha mai usato un Raspberry:
[docs/installazione.md](docs/installazione.md).

```
sudo apt install -y git python3-venv python3-pil
git clone https://github.com/Hapoyo/PiDash.git ~/pi-dash
cd ~/pi-dash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m dash --once --demo --driver sim   # prova: scrive out/frame.png
scripts/installa-servizio.sh && sudo systemctl start pi-dash   # avvio automatico
```

### 3.1 Aggiornamento
```
~/pi-dash/scripts/aggiorna.sh
```
Scarica da GitHub, esegue i test, riavvia il servizio; se qualcosa non va torna alla versione
precedente. Dettagli e passaggio da un'installazione via zip: guida § 7.

## 4. Configurazione
Lo schedario si cambia dalla scheda **+** senza toccare i file: B (o il tocco su una voce) sceglie,
A (o il tocco sul "+") conferma. Le schede opzionali sono elencate in `new.tipi`; la scelta
finisce in `config.local.json`.

`config.json` (in Git) contiene i valori del progetto: posizione, sveglie, preset del timer,
pagine, colori, touch. Le modifiche fatte sul Raspberry vanno in `config.local.json`
(fuori da Git, solo le voci da cambiare): gli aggiornamenti non le toccano.
Schedario, voci, calibrazione del tocco, animazioni e colori: guida § 5.6, § 5.7, § 5.4, § 9.1
e § 9.2.

## 5. Sviluppo senza hardware
```
python -m dash --demo --driver sim --web 8080   # simulatore nel browser
python -m dash --screenshots docs/img           # rigenera anteprime e GIF del README
python -m dash --demo --driver sim --motion off # senza animazioni
python -m unittest -v                           # 59 test
```
Regole del progetto e decisioni: [CLAUDE.md](CLAUDE.md). Modifiche: [CHANGELOG.md](CHANGELOG.md).

## 6. Font
Space Grotesk e Space Mono: SIL Open Font License 1.1 (licenze in `fonts/`).
