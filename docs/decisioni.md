# pi-dash — Decisioni di progetto

Versione 0.5.0 · 2026-09-27

Scelte prese e motivi. Da leggere prima di cambiare il comportamento di una parte;
le regole operative stanno in [CLAUDE.md](../CLAUDE.md).

## 1. Decisioni
- Schedario: una linguetta numerata per pagina. Le pagine precedenti restano in pila in alto, le
  successive in pila in basso; la cartella aperta parte dalla propria linguetta. Geometria unica in
  `render/folders.layout(w, h, n, current)`, usata sia dal disegno sia dal tocco.
- Home: ora, data, luogo e coordinate, alba/tramonto, barra della giornata, settimana n:X,
  giorno X/365 (366 negli anni bisestili), tre anelli concentrici (anno arancio, mese ambra,
  settimana crema) con una sfera in testa all'arco: `ClockWidget.cycles`.
- Schedario componibile: la scheda "+" (`widgets/new.py`) elenca solo i tipi opzionali
  (`new.tipi`, di norma timer e sveglia); ogni voce fa da interruttore, quindi una sola pagina
  per tipo. `App.add_page`/`remove_page` creano il widget e salvano `pages` in
  `config.local.json`; `App.page_kinds()` dice al widget cosa è già presente. Chiave della pagina
  `tipo` o `tipo#N`, sempre libera anche dopo una rimozione (più copie restano possibili da
  configurazione). La scheda "+" resta ultima e non si può togliere.
- Meteo: direzione del vento come anello della home (`pages/weather._wind_ring` → `cv.ring`): arco
  da nord in senso orario fino alla direzione **da cui** soffia il vento (uso nautico), sfera in
  testa, gradi al centro, tacca sul nord. Niente aghi né radar. `cv.panel(reserve=...)` libera lo
  spazio a destra del numero.
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
- Motion graphics: pagina base ridisegnata solo se cambia `state_key`; `App.step` compone
  `motion.fps` fotogrammi al secondo sopra di essa. Budget SPI: 480×320×16 bit ≈ 2,46 Mbit, a
  18 MHz ≈ 0,14 s per schermo intero → `fb.py` scrive solo le fasce di 16 righe cambiate.
  Numeri `live` (cpu, timer) si decodificano solo all'apertura della pagina. Con allarme attivo
  gli effetti continui si fermano. `--once` e `--screenshots` danno fotogrammi fermi.
- Da collaudare sull'hardware: overlay e framebuffer, orientamento del touch, pulsanti GPIO, cicalino,
  fluidità delle animazioni e aggiornamento parziale del pannello (damage del driver DRM).
- Griglia di disegno: misure pensate per lo schermo reale 480×320 (non più per 960×540 scalato):
  sotto i 12 px Space Mono diventa illeggibile sul 3,5". Le linguette costano altezza: con 6
  pagine restano ~170 px utili, per questo i pannelli bassi passano a una riga sola e la
  previsione meteo toglie la terza riga quando non ci sta.
