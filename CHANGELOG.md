# Changelog

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
