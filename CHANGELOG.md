# Changelog

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
