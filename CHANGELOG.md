# Changelog

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
