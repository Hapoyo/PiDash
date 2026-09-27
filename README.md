# PiDash

> Versione 0.6.1 · 2026-09-27

Cruscotto da tavolo per Raspberry Pi con schermo touch SPI da 3,5": ora, meteo con vento in nodi,
timer di partenza regata, sveglia e stato del sistema, in un'interfaccia a schedario ispirata ai
computer di bordo.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![Raspberry Pi 3](https://img.shields.io/badge/Raspberry%20Pi-3%20Model%20B-C51A4A?logo=raspberrypi&logoColor=white)
![Schermo 480×320](https://img.shields.io/badge/schermo-480%C3%97320%20SPI-5b514a)
![Dipendenze](https://img.shields.io/badge/dipendenze-Pillow-ee7b50)

![Accensione, cambio pagina e numeri che si decodificano](docs/img/animazione.gif)

## 1. Caratteristiche

- **Schedario componibile**: ogni funzione è una cartella con la sua linguetta; timer e sveglia si
  aggiungono e si tolgono direttamente dallo schermo, dalle **Impostazioni** (linguetta con
  l'ingranaggio), dove si regolano anche luminosità e calibrazione del tocco e si spegne il Pi.
- **Tocco preciso**: ogni bottone risponde da solo, un tocco appena fuori vale per il più vicino,
  il punto è la mediana dei campioni letti mentre il dito preme.
- **Meteo per chi va in mare**: vento in nodi con direzione, raffiche e forza Beaufort, pressione,
  pioggia e previsione a 15 ore da [Open-Meteo](https://open-meteo.com), senza chiave API.
- **Timer di partenza regata**: il tempo si compone sommando i bottoni (+1′, +5′, +10′, +15′,
  −1′, C per azzerare); **sveglie settimanali**.
- **Posizione precisa**: GPS se c'è un ricevitore, altrimenti le reti Wi-Fi vicine, poi l'IP.
- **Controllo dell'alimentazione**: grafico degli ultimi 48 minuti e avviso in rosa quando la
  tensione in ingresso scende sotto 4,63 V (rilevatore di sottotensione del Raspberry).
- **Funziona anche senza rete**: alba e tramonto calcolati in locale, ultimo meteo in cache.
- **Motion graphics leggere**: sequenza di accensione, transizioni, cifre che si decodificano,
  pensate per il bus SPI (si aggiornano solo le righe cambiate).
- **Nessun desktop richiesto**: disegna direttamente nel framebuffer su Raspberry Pi OS Lite.
- **Aggiornamento con un comando**, con test e ritorno automatico alla versione precedente.
- **Una sola dipendenza Python**: Pillow.

## 2. Schermate

| # | Pagina | Presente | Contenuto |
|---|---|---|---|
| 001 | Home | sempre | ora e data, luogo e coordinate, alba/tramonto, avanzamento del giorno, anelli di settimana, mese e anno |
| 002 | Meteo | sempre | temperatura, vento (nodi, direzione, raffiche, Beaufort), pioggia, umidità, pressione, previsione oraria, fase lunare |
| 003 | Timer | a scelta | conto alla rovescia composto con i bottoni; 5′ = sequenza di partenza |
| 004 | Sveglia | a scelta | prossima sveglia, stato, sveglie per giorno della settimana |
| 005 | Sistema | sempre | CPU, RAM, disco, storici di CPU e rete, host, IP, temperatura, uptime |
| ⚙ | Impostazioni | sempre | schede opzionali, luminosità, calibrazione del tocco, spegnimento, grafico della tensione di alimentazione |

| 001 · Home | 002 · Meteo |
|:---:|:---:|
| ![Home](docs/img/01-home.png) | ![Meteo](docs/img/02-meteo.png) |
| **003 · Timer** | **004 · Sveglia** |
| ![Timer](docs/img/03-timer.png) | ![Sveglia](docs/img/04-sveglia.png) |
| **005 · Sistema** | **⚙ · Impostazioni** |
| ![Sistema](docs/img/05-sistema.png) | ![Impostazioni](docs/img/06-new.png) |

Schermate fuori dallo schedario:

| Avvio (5 s, un tocco lo salta) | Spegni: il primo tocco chiede conferma |
|:---:|:---:|
| ![Avvio](docs/img/avvio.png) | ![Conferma dello spegnimento](docs/img/spegni-conferma.png) |
| **Tensione sotto 4,63 V: grafico e linguetta in rosa** | **Calibra touch: quattro croci, una alla volta** |
| ![Tensione bassa](docs/img/tensione-bassa.png) | ![Calibrazione del touch](docs/img/calibrazione.png) |
| **Spegnimento** | |
| ![Spegnimento](docs/img/spegnimento.png) | |

Immagini a 480×320, risoluzione nativa dello schermo, generate dal codice con dati dimostrativi.

## 3. Requisiti

| Componente | Specifica |
|---|---|
| Scheda | Raspberry Pi 3 Model B, Raspberry Pi OS Lite 64 bit |
| Schermo | "3.5inch RPi Display" 480×320, controller ILI9486, touch XPT2046 (overlay `piscreen,drm`) |
| Alimentatore | 5,1 V · 2,5 A |
| Opzionali | pulsanti fisici su GPIO 5/13/19, cicalino su GPIO 26, ricevitore GPS USB |
| Software | Python ≥ 3.11, Pillow ≥ 10.1 |
| Rete | facoltativa: serve per meteo e posizione, non per ora, alba e tramonto |

Collegamenti, overlay e banda del bus SPI: [docs/hardware.md](docs/hardware.md).

## 4. Installazione

Guida completa passo per passo, anche per chi usa un Raspberry per la prima volta:
[docs/installazione.md](docs/installazione.md). In sintesi, sul Raspberry:

```bash
sudo apt install -y git python3-venv python3-pil
git clone -b main https://github.com/Hapoyo/PiDash.git ~/pi-dash
cd ~/pi-dash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m dash --once --demo --driver sim   # prova: scrive out/frame.png
scripts/installa-servizio.sh && sudo systemctl start pi-dash
```

### 4.1 Aggiornamento

```bash
~/pi-dash/scripts/aggiorna.sh
```

Lo script scarica la nuova versione, aggiorna le dipendenze, esegue i test e riavvia il servizio.
Se un controllo fallisce ripristina da solo la versione precedente. Passaggio da un'installazione
copiata a mano: guida, § 7.1.

## 5. Configurazione

La configurazione è su due livelli:

- `config.json`, nel repository: i valori del progetto;
- `config.local.json`, solo sul Raspberry e fuori da Git: le impostazioni personali. Contiene solo
  le voci da cambiare, ha la precedenza e non viene toccato dagli aggiornamenti.

| Voce | Significato | Predefinito |
|---|---|---|
| `location.mode` | posizione: `auto` (GPS, poi Wi-Fi, poi IP), `ip`, `city` (per nome), `fixed` (coordinate) | `auto` |
| `location.name`, `lat`, `lon` | luogo e coordinate di riserva | Gaeta, 41,214 N 13,571 E |
| `location.wifi`, `gps_device` | posizione dalle reti Wi-Fi (BeaconDB); seriale del GPS | `true`; automatica |
| `timer.presets_s`, `timer.labels` | bottoni che sommano il tempo (secondi) ed etichette | 60, 300, 600, 900 · 300 = "partenza" |
| `backlight.level`, `backlight.mode` | luminosità 10–100; `auto`, `hw` (LED), `sw` (immagine) | 100, `auto` |
| `alarm.alarms` | sveglie: ora, giorni (0 = lunedì), attiva | 07:00, lunedì–venerdì |
| `motion.livello`, `motion.fps` | animazioni: `pieno`, `eventi`, `off`; fotogrammi al secondo | `pieno`, 8 |
| `theme.palette` | colori dell'interfaccia, per nome (`orange`, `amber`…) | tema originale |
| `input.touch` | calibrazione del tocco (Impostazioni → calibra touch) | automatica |
| `display.rotate` | rotazione dell'immagine: 0, 90, 180, 270 | 0 |

Esempio di `config.local.json`:

```json
{
  "location": {"mode": "fixed", "name": "Ventotene", "lat": 40.796, "lon": 13.436},
  "motion": {"livello": "eventi"}
}
```

Timer e sveglia si aggiungono dalle **Impostazioni** con un tocco sulla voce (coi pulsanti: B
sceglie, A conferma). Luminosità, calibrazione del tocco e spegnimento stanno nella stessa scheda.
Voci complete: guida, § 5 e § 9.

### 5.1 Animazioni

| Effetto | Quando | Livello |
|---|---|---|
| Accensione: sigla "Pi-Dash", righe di controllo, barra di carico (5 s; un tocco la salta) | all'avvio | eventi |
| Scansione dall'alto con riga arancio | al cambio pagina | eventi |
| Cifre che scorrono e si fermano | numeri che cambiano, apertura della pagina | eventi |
| Due punti che lampeggiano | ora, timer in corsa | pieno |
| Aloni attorno alle sfere | anelli della home e del vento | pieno |
| Spia della linguetta aperta | tutte le pagine | pieno |

Durante un allarme gli effetti continui si fermano.

## 6. Sviluppo

Non serve l'hardware: il simulatore disegna le stesse immagini in PNG e le mostra nel browser.

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m dash --demo --driver sim --web 8080   # simulatore: http://localhost:8080
python -m dash --screenshots docs/img           # rigenera anteprime e GIF
python -m unittest -v                           # 60 test
```

### 6.1 Architettura

```
dash/
  app.py          ciclo dell'applicazione, pagine, eventi
  main.py         riga di comando
  config.py       configurazione a due livelli e validazione
  location.py     posizione: GPS, Wi-Fi, IP, città, fissa
  backlight.py    luminosità: retroilluminazione o immagine scurita
  motion.py       tempi delle animazioni
  widgets/        dati e stato di ogni pagina (nessun disegno)
  render/         disegno: tema e griglia, primitive, schedario, una pagina per modulo, effetti
  display/        uscite: framebuffer Linux e simulatore
```

Ogni pagina è un widget (dati) più una funzione di disegno in `dash/render/pages/`. Misure e
colori stanno in un solo punto, `dash/render/theme.py`. Regole di stile del codice e convenzioni:
[CLAUDE.md](CLAUDE.md); motivazioni delle scelte: [docs/decisioni.md](docs/decisioni.md).

### 6.2 Flusso di lavoro

Ogni modifica passa da un ramo e da una pull request verso `main`. Il Raspberry si aggiorna solo
da `main`, e solo se tutti i test passano. Storico delle versioni: [CHANGELOG.md](CHANGELOG.md).

## 7. Documentazione

| Documento | Contenuto |
|---|---|
| [docs/installazione.md](docs/installazione.md) | installazione, schermo, calibrazione, avvio automatico, aggiornamento, problemi comuni |
| [docs/hardware.md](docs/hardware.md) | pin, overlay, alimentazione, banda del bus SPI |
| [docs/decisioni.md](docs/decisioni.md) | scelte di progetto e motivi |
| [CHANGELOG.md](CHANGELOG.md) | modifiche per versione |

## 8. Crediti e licenze

- **Dati meteo e geocodifica**: [Open-Meteo.com](https://open-meteo.com), dati con licenza
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). L'API gratuita è riservata all'uso
  non commerciale ([termini](https://open-meteo.com/en/terms)).
- **Posizione dall'indirizzo IP**: ipapi.co, con ip-api.com come riserva.
- **Caratteri**: Space Grotesk e Space Mono, SIL Open Font License 1.1 (testi in `fonts/`).
- **Codice**: il repository non contiene ancora un file di licenza; finché non viene aggiunto,
  valgono i diritti d'autore predefiniti.
