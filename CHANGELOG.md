# Changelog

## 0.10.0 — 2026-10-03
- **Parlare a Needle dal telefono**: con `voce.porta` (es. 8443) pi-dash serve in HTTPS una pagina
  con un bottone "premi e parla". Il browser del telefono riconosce la voce in italiano e manda al
  Pi solo il testo, eseguito come una frase della scheda Needle; l'esito torna sul telefono.
  Casella per scrivere o dettare con la tastiera e frasi di `needle.queries` come scorciatoie.
  Certificato autofirmato creato da `openssl` in `out/voce/`, oppure quello di Tailscale
  (`voce.cert`, `voce.key`); codice d'accesso facoltativo `voce.token`. Guida § 5.13.
- **QR sulla scheda Needle**: con la pagina "premi e parla" accesa, un tocco sul bot mostra il QR
  dell'indirizzo (con il codice d'accesso); un altro tocco riporta il bot. QR generato senza
  dipendenze (`dash/qr.py`). L'indirizzo si ricalcola ogni minuto, così segue l'IP del Pi se il
  Wi-Fi arriva tardi o il router ne assegna un altro.
- La pagina è **accesa di serie** (`voce.porta` 8443 in `config.json`): al primo avvio pi-dash
  crea un codice d'accesso casuale e lo salva in `config.local.json`; il QR lo contiene già.
- **Interprete di frasi** (`dash/frasi.py`): timer, sveglie e luci chiesti in italiano li capisce
  il codice, senza il modello e anche con il servizio Needle spento. Durate in ogni forma ("un'ora
  e mezza", "un quarto d'ora"), orari ("alle 8 meno un quarto"), giorni della settimana, stanze,
  colori, temperatura del bianco, luminosità relativa ("abbassa il soggiorno"). Nuove azioni:
  ferma, pausa e riprendi il timer, sveglie solo in certi giorni e cancellazione, luci colorate.
  Si spegne con `needle.regole: false`. Guida § 5.11.
- **Azioni personalizzate** (`needle.azioni`, fino a 30): una frase chiave ("pasta", "buonanotte")
  avvia insieme timer, sveglia, luci e pagina. Tre esempi in `config.json`.
- **Bot di Needle**: una testa di robot mostra lo stato del modello (spento, controllo, pronto,
  penso, fatto, dubbio, errore) e si muove con `motion.livello` `pieno`. Guida § 5.12.
- **Scheda Needle più semplice**: niente più pannello con frase, funzione e confidenza; restano
  una riga con l'esito e lo stato, il bot a sinistra e i bottoni delle frasi a destra, più grandi.
- **Cambiare rete Wi-Fi**: `python -m dash --wifi [SSID]` chiede la password nascosta, aggiorna o
  crea il profilo con `nmcli`, si collega e avvisa se la rete è solo a 5 GHz. La password resta a
  NetworkManager. Guida § 3.1.
- **Bridge Hue che cambia indirizzo**: se non risponde, pi-dash lo ritrova in rete, controlla che
  la chiave funzioni, ripete il comando e salva il nuovo indirizzo in `config.local.json`.
- Anteprime: nuova schermata `needle-qr.png`; le anteprime mostrano la pagina "premi e parla"
  accesa, come nel `config.json` del progetto, con un indirizzo e un codice d'esempio.
- Documentazione allineata alla versione: README (funzioni, requisiti, architettura, crediti),
  guida, decisioni, note hardware.

## 0.9.1 — 2026-09-29
- **Accendere le luci a un livello**: "accendi il soggiorno al 100%", "…al 100 per cento" e "…al
  massimo" accendono la stanza a quella luminosità. Il modello, con queste frasi, risponde
  `lights_off` e perdeva il livello: lo legge il dashboard dal testo, come già faceva per il
  verso. Livello da 1 a 100, fuori scala non si esegue; spegnendo è ignorato.

## 0.9.0 — 2026-09-29
- **Luci Philips Hue con Needle**: "accendi il soggiorno", "spegni tutte le luci", "soppalco al
  30 per cento". Funzioni `lights_on`, `lights_off`, `set_brightness` (stanza e percentuale); le
  stanze sono quelle del bridge, riconosciute senza accenti né articoli, e un nome ambiguo o
  sconosciuto non si esegue. L'esito dice anche se le luci non sono raggiungibili.
- Sicurezza: il modello scambiava "accendi" e "spegni", quindi **il verbo della frase decide il
  verso** e una negazione blocca; **la luminosità deve comparire nel testo**. Soglia propria per le
  luci (`needle.soglia_luci`, 0,4).
- `python -m dash --hue-registra [IP]`: registra PiDash sul bridge (tasto premuto entro 30 s) e
  salva la chiave in `config.local.json`, mai a video. `save_local` conserva i permessi del file
  (un file nuovo nasce a 600) perché ora contiene la chiave.
- Config: sezione `hue` (`bridge`, `key`, `timeout_s`), vuota in `config.json`.
- `needle/tools.json`: 13 funzioni; descrizioni delle luci scritte per il modello (senza, la
  luminosità veniva scambiata per accendi/spegni).

## 0.8.0 — 2026-09-29
- **Needle esegue le funzioni**: la scheda non si limita più a mostrarle. `start_timer_minutes` e
  `start_timer_seconds` impostano e avviano il timer, `set_alarm` aggiunge una sveglia (ogni
  giorno, salvata in `config.local.json`), `open_*` apre una pagina, `get_weather` apre il meteo.
  In alto nella scheda compare l'esito (`→ timer 5' avviato`). Se la pagina Timer o Sveglia manca
  viene creata.
- `needle/tools.json` rifatto sulla misura del modello: timer separato per minuti e secondi (con
  un'unica funzione "timer di 90 secondi" avviava 90 minuti) e una funzione per pagina al posto
  di `show_page(page)`. Dopo l'aggiornamento: `sudo systemctl restart needle` (lo fa `aggiorna.sh`).
- Sicurezza: elenco fisso di funzioni (`dash/azioni.py`), argomenti controllati prima di cambiare
  qualcosa, nessuna funzione per spegnere il Pi. Nessuna esecuzione sotto `needle.soglia` (0,6)
  per timer e sveglia e sotto `needle.soglia_pagine` (0,35) per le funzioni che aprono solo una
  pagina. Le azioni girano nel ciclo principale, non nel thread della richiesta.
- Config: `needle.esegui`, `needle.soglia`, `needle.soglia_pagine`, `needle.naviga`. Frasi di
  prova senza la sveglia ("meteo a ventotene", "timer 5 minuti", "apri la pagina sistema",
  "vai alla home").

## 0.7.0 — 2026-09-29
- **Scheda Needle**: nuova pagina opzionale (`+ needle` nelle Impostazioni) per il modello locale
  [Needle](https://github.com/cactus-compute/needle) (function calling). Mostra lo stato del
  servizio (pronto, penso…, offline), invia a scelta una delle frasi di `needle.queries` e mostra
  la funzione riconosciuta con confidenza e tempo (`get_weather(city=Ventotene)` · 95 % · 2,2 s).
  Richieste in thread: il disegno non aspetta mai il modello.
- **Servizio `needle`**: `systemd/needle.service` e `scripts/installa-needle.sh`, sul modello di
  pi-dash. API locale su `127.0.0.1:8090` (non esposta alla rete), memoria limitata a 300 MB.
- `needle/tools.json`: funzioni note al modello (`get_weather`, `start_timer`, `set_alarm`,
  `show_page`). Per ora la scheda le mostra soltanto, non le esegue.
- Config: sezione `needle` (`url`, `timeout_s`, `reset`, `queries`) e `needle` in `new.tipi`.
- README: anteprima della scheda; le anteprime hanno ora sette linguette (`06-needle.png`,
  `07-new.png`).

## 0.6.1 — 2026-09-27
- Impostazioni: nuova riga **tensione** in fondo, con il grafico degli ultimi 48 minuti (una
  colonna al minuto, rosa dove l'alimentazione è scesa sotto 4,63 V), il numero di cali e l'ora
  dell'ultimo. Con la tensione bassa adesso il riquadro lampeggia e la linguetta delle
  Impostazioni diventa rosa con "tensione bassa", su ogni pagina.
- Fonte: il rilevatore di sottotensione del Raspberry (hwmon `rpi_volt`, in ripiego
  `vcgencmd get_throttled`), letto ogni 5 s (`power.sample_s`); `power.monitor: false` lo spegne.
  Il Pi 3 non misura i volt: il grafico dice sopra o sotto soglia.
- README: anteprima "tensione bassa" fra le schermate di sistema.

## 0.6.0 — 2026-09-27
- **Impostazioni** al posto della scheda "+": linguetta con l'ingranaggio e tre righe,
  - schede: timer e sveglia si aggiungono o tolgono con **un solo tocco** sulla voce;
  - luminosità: − / + dal 10 al 100 %, salvata in `config.local.json`; LED vero se il pannello
    lo espone in `/sys/class/backlight`, altrimenti immagine scurita (`dash/backlight.py`);
  - sistema: **calibra touch** (quattro croci, estremi e orientamento calcolati e applicati
    senza riavvio) e **spegni**, con secondo tocco di conferma e schermata di spegnimento.
- **Tocco più preciso**: il punto è la mediana dei campioni letti mentre il dito preme (scartati
  appoggio e distacco); ogni pagina espone i suoi bottoni (`hits`) e un tocco a meno di 12 px da
  un bottone vale per quello; antirimbalzo da 0,3 a 0,15 s.
- **Timer a somma**: bottoni −1′ · +1′ · +5′ · +10′ · +15′ · C. I preset si sommano a ogni tocco,
  anche mentre il tempo scorre; il tocco sul tempo avvia e mette in pausa.
- **Posizione**: nuovo modo `auto`, predefinito: GPS (gpsd o NMEA), poi reti Wi-Fi (BeaconDB),
  poi IP, poi coordinate fisse (ora Gaeta). La home indica la fonte (gps, wifi, ip). L'IP da solo
  mostrava Lavinio, il nodo del provider.
- Avvio più lento (5 s invece di 2,4) con la sigla **Pi-Dash**.
- Home: l'ora sale di altri 5 px, alla stessa taglia.
- Servizio: retroilluminazione scrivibile all'avvio; `installa-servizio.sh` aggiunge
  `/etc/sudoers.d/pi-dash` (solo `systemctl poweroff`). `aggiorna.sh` lo reinstalla da solo.
- Simulatore web: un clic sull'anteprima è un tocco. Su Windows il simulatore non si ferma più
  per la mancanza del touch.

## 0.5.2 — 2026-09-27
- README riscritto con tono professionale: caratteristiche, schermate, requisiti, installazione,
  tabella delle voci di configurazione con i valori predefiniti, architettura, flusso di lavoro,
  crediti e licenze (Open-Meteo CC BY 4.0 e uso non commerciale, font OFL, codice senza licenza).
- Installazione: `git clone -b main`, così il Raspberry segue sempre il ramo stabile anche se il
  ramo predefinito del repository è un altro (README e guida § 4.3, § 7.1).

## 0.5.1 — 2026-09-27
- Home: l'ora sale di mezzo passo di griglia e non tocca più la data. A 480×320 fra le cifre
  e il giorno restavano 3 px (le cifre tonde scendono sotto la linea di base, la data sale
  sopra la sua riga); ora sono 6, il passo `gap`. Cifre 3 px più basse, resto invariato.
- CLAUDE.md: lo sviluppo passa solo da Claude Code e GitHub, con unione sempre in `main`.

## 0.5.0 — 2026-09-27
- Codice riorganizzato, a parità di immagine (95 impronte identiche: pagine a quattro
  risoluzioni, compresa quella ruotata, e ogni fotogramma della GIF):
  - `dash/cyber.py` (850 righe) diviso nel pacchetto `dash/render/`: `theme`, `canvas`
    (primitive dello stile), `folders` (schedario), `pages/` (un modulo per pagina con registro
    `PAGES`), `effects` (animazioni e allarme), `renderer`;
  - `dash/main.py` diviso in `app.py` (ciclo e pagine), `preview.py` (anteprime) e `main.py`
    (sola riga di comando);
  - tolto il driver `waveshare`, che la validazione rifiutava già;
  - decisioni di progetto spostate da `CLAUDE.md` a `docs/decisioni.md` (CLAUDE.md sotto le
    150 righe).
- Grafica più leggibile e allineata su tutte le schermate:
  - griglia unica in `render/theme.py` (`GRID`): margini, spazi, raggi, spessori e due corpi di
    testo pensati per lo schermo 480×320; le pagine non usano più numeri sparsi;
  - etichette da 8 a 12 px, testi secondari 11 px, linguette alte 18–20 px (più facili da
    toccare);
  - pannelli con etichetta, numero e dettaglio allineati a sinistra; i pannelli bassi (pioggia,
    umidità, pressione, "prossima" della sveglia) mettono etichetta e numero sulla stessa riga;
  - home: ora, data e righe allineate a sinistra, anelli più grandi; meteo: anello del vento alto
    quanto il pannello, previsione che rinuncia alla riga vento/pioggia se lo spazio non basta;
    sistema: dati della macchina su due colonne con i valori incolonnati; timer: niente più
    "pronto pronto"; scheda "+": simbolo alto quanto il pannello.
- Test sulle misure minime di leggibilità a 480×320 (60 test).

## 0.4.1 — 2026-09-26
- Meteo: al posto della bussola con riga e radar, un anello come quelli della home — arco da
  nord in senso orario fino alla direzione da cui soffia il vento, sfera in testa, gradi al
  centro, tacca sul nord. L'etichetta del pannello torna al solo nome del vento.
- Sistema: tolto il cursore che scorreva sui grafici di CPU e rete.
- Test resi deterministici: il ciclo si prova con un istante fisso (prima poteva fallire a caso
  se due giri cadevano a cavallo dei 2 s della pagina sistema, più probabile sul Pi); la GIF si
  controlla sulla durata totale, perché Pillow unisce i fotogrammi uguali consecutivi.

## 0.4.0 — 2026-09-26
- Motion graphics (`dash/motion.py` per i tempi, `CyberRenderer.compose` per il disegno):
  - a evento: sequenza di accensione (sigla, righe di controllo, barra di carico; un tocco la
    salta), scansione dall'alto con riga arancio al cambio pagina, cifre dei numeri grandi che si
    decodificano quando cambiano o quando si apre la pagina (07:42 → 07:43 muove solo l'ultima);
  - continui: due punti che lampeggiano, aloni sulle sfere degli anelli, radar sulla bussola,
    cursore sui grafici di CPU e rete, spia della linguetta aperta.
- `motion.livello` = `pieno` (predefinito) · `eventi` · `off`, `motion.fps` (predefinito 8),
  `motion.avvio`; opzione `--motion` da riga di comando.
- La pagina si disegna una volta come livello base e si ridisegna solo quando cambiano i dati;
  ogni fotogramma animato aggiunge sopra solo ciò che si muove.
- Cache dei testi già rasterizzati: disegno di una pagina da 10–31 ms a 1–3 ms (misurato su PC).
- Framebuffer: si scrivono solo le fasce di righe cambiate, meno traffico sul bus SPI.
- Simulatore web aggiornato ogni 120 ms, per vedere le animazioni.
- `--screenshots` salva anche `animazione.gif` per il README.
- 59 test.

## 0.3.1 — 2026-09-26
- Corretto: `scripts/aggiorna.sh` falliva sul Raspberry quando `config.local.json` cambiava
  `pages`, perché il test del `config.json` di progetto leggeva anche le impostazioni locali.
  Ora quel test usa una copia isolata del file.
- Chi aggiorna da uno schedario personale senza la scheda "+" trova nel log l'avviso con la riga
  da aggiungere (`{"name": "+", "widget": "new"}`): senza quella scheda timer e sveglia non si
  possono aggiungere dallo schermo.
- 47 test.

## 0.3.0 — 2026-09-26
- Schedario componibile: la scheda "+" elenca le schede opzionali (`new.tipi`: timer e sveglia) e
  ogni voce fa da interruttore — aggiunge la scheda se manca, la toglie se c'è. La scelta si salva
  in `config.local.json`. B sceglie la voce, A conferma; col tocco: una voce per scegliere,
  il "+" per confermare.
- Timer e sveglia non sono più pagine fisse: si aggiungono dal "+" quando servono.
- Home: tre anelli concentrici con una sfera ciascuno per settimana, mese e anno.
- Meteo: bussola con una riga dagli estremi arrotondati verso la direzione da cui soffia il vento
  (niente ago) e gradi nell'etichetta del pannello.
- Sistema: storico del traffico di rete accanto a quello della CPU e riga "rete" con
  le velocità in ingresso e in uscita (lette da `/proc/net/dev`, esclusa `lo`).
- Corretto: `--driver sim` su una configurazione da Raspberry (`width`/`height` "auto") faceva
  fallire il comando di prova indicato nel README; ora le dimensioni valgono 480×320 con qualunque
  driver diverso da `fb`.
- 46 test.

## 0.2.0 — 2026-09-26
- README: anteprime di tutte e cinque le pagine (`docs/img/01-home.png` … `05-sistema.png`)
  al posto dell'unica immagine `docs/img/home.png`.
- Nuova opzione `--screenshots DIR`: salva un PNG per pagina con dati demo (meteo e sistema),
  posizione fissa e istante fisso, senza rete; le anteprime restano allineate al codice.
- Widget sistema: `load_demo()` con statistiche finte per le anteprime.
- Indirizzo del repository (`Hapoyo/PiDash`) in README e guida di installazione.
- Aggiornamento dal repository: `scripts/aggiorna.sh` scarica, aggiorna le dipendenze, esegue
  test e verifica della configurazione, riavvia il servizio; se qualcosa fallisce torna alla
  versione precedente. Guida § 7 riscritta, con passaggio dall'installazione via zip (§ 7.1).
- Impostazioni del singolo Raspberry in `config.local.json` (fuori da Git, fuse sopra
  `config.json`): `git pull` non trova più conflitti. Guida § 5.6.
- `scripts/installa-servizio.sh` sostituisce il `sed` della guida, che trasformava anche
  `/home/pi/pi-dash` in `/home/<utente>/<utente>-dash` e modificava un file in Git.
- 38 test.

## 0.1.0 — 2026-09-25
Prima pubblicazione.

- Dashboard per Raspberry Pi 3 Model B con schermo SPI 3,5" (ILI9486 + touch XPT2046), scritto
  direttamente nel framebuffer: nessun desktop necessario.
- Cinque pagine a schedario: Home, Meteo, Timer, Sveglia, Sistema; si cambia toccando la linguetta.
- Stile unico: pannelli arrotondati a colori su fondo scuro, numeri in Space Grotesk,
  microetichette in Space Mono, colori personalizzabili da `config.json`.
- Meteo e vento in nodi da Open-Meteo (senza chiave), alba e tramonto calcolati in locale.
- Avvio automatico con systemd, simulatore web per lo sviluppo senza hardware, 35 test.
