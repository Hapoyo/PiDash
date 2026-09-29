# pi-dash — Decisioni di progetto

Versione 0.9.1 · 2026-09-29

Scelte prese e motivi. Da leggere prima di cambiare il comportamento di una parte;
le regole operative stanno in [CLAUDE.md](../CLAUDE.md).

## 1. Decisioni
- Needle (`widgets/needle.py`, `render/pages/needle.py`): il modello gira in un **servizio
  systemd separato** (`systemd/needle.service`), non dentro pi-dash, perché è un binario nativo
  con la sua RAM (75 MB, limite 300 MB) e un crash non deve fermare lo schermo. Ascolta solo su
  `127.0.0.1:8090` (il binario non ha autenticazione), quindi pi-dash lo raggiunge in locale e la
  LAN no. Il widget non blocca mai il disegno: controllo TCP ogni 5 s e richieste a `/complete` in
  thread; `POST /reset` prima di ogni frase (`needle.reset`), altrimenti il server accumula i
  turni in un'unica conversazione. La scheda è opzionale (catalogo del "+", `new.tipi`).
- Luci Hue (`dash/hue.py`, funzioni `lights_on/off` e `set_brightness` in `azioni.py`): API v1 del
  bridge su HTTPS, che basta per stanze e luminosità; certificato autofirmato non verificato (rete
  locale, indirizzo scritto in configurazione), chiave solo in `config.local.json` a 600
  (`save_local` ne conserva i permessi) e mai in URL di errore, log o schermo. Una funzione per
  stanza sarebbe troppe funzioni per il modello: il nome della stanza è un argomento testuale,
  confrontato dal dashboard con le stanze vere senza indovinare (esatta, poi parziale se unica,
  altrimenti "ambigua"). Provato sul modello con 16 frasi: la stanza è sempre giusta, il verso no
  ("accendi tutte le luci" → `lights_off`) e la confidenza sta fra 0,4 e 0,6 anche per risposte
  corrette. Perciò il verbo della frase decide accendere o spegnere, la negazione blocca, la
  luminosità deve essere nel testo, e le luci hanno una soglia propria (0,4) invece di 0,6.
  Per lo stesso motivo "accendi il soggiorno al 100%" (per il modello `lights_off`, 0,52) prende
  il livello dal testo (`azioni._livello`: "N%", "N per cento", "al massimo"), altrimenti
  accenderebbe alla luminosità di prima.
  Chiamate sincrone con timeout di 2 s: un bridge spento rallenta il dashboard, non lo blocca; un
  thread avrebbe complicato l'esito mostrato in scheda per un caso raro.
- Azioni di Needle (`dash/azioni.py`): il modello propone, il dashboard decide. Il thread della
  richiesta non tocca mai il dashboard: mette le chiamate in coda (`NeedleWidget.take_calls`) e le
  esegue `App.step` nel ciclo principale, dove si cambiano pagine e widget. Solo le funzioni di
  `AZIONI` (timer, sveglia, apri pagina, meteo), argomenti controllati prima di creare o cambiare
  qualcosa, e nessuna funzione irreversibile (niente spegnimento). Sotto `needle.soglia` (0,6) non
  si esegue. Le funzioni sono disegnate sul modello, misurato sul Pi con 17 frasi italiane: con
  `start_timer(minutes)` e `show_page(page)` "timer di 90 secondi" avviava 90 minuti (confidenza
  0,71) e "apri sistema" non veniva riconosciuto; con una funzione per unità di tempo e una senza
  argomenti per pagina le frasi giuste passano da 10 a 12 su 17 e l'unità è sempre corretta. La
  confidenza non è tarata sull'italiano e per le funzioni senza argomenti è bassa anche quando
  la scelta è giusta (0,38–0,59), mentre timer e sveglia stanno fra 0,8 e 0,95. Due soglie, in base
  al danno di un errore: 0,6 per ciò che cambia lo stato (timer, sveglia), 0,35 per ciò che apre
  solo una pagina (`azioni.solo_pagina`). Con 0,6 per tutto i comandi di navigazione non
  funzionerebbero quasi mai; con 0,35 per tutto un timer sbagliato partirebbe. La sveglia è ogni giorno (le sveglie non hanno ancora un "una volta sola") e non si
  toglie dallo schermo, quindi al massimo 10 e mai duplicate. Frasi di prova senza sveglie: un
  tocco di curiosità non deve programmare la sveglia di domani.
- Schedario: una linguetta numerata per pagina. Le pagine precedenti restano in pila in alto, le
  successive in pila in basso; la cartella aperta parte dalla propria linguetta. Geometria unica in
  `render/folders.layout(w, h, n, current)`, usata sia dal disegno sia dal tocco.
- Home: ora, data, luogo e coordinate, alba/tramonto, barra della giornata, settimana n:X,
  giorno X/365 (366 negli anni bisestili), tre anelli concentrici (anno arancio, mese ambra,
  settimana crema) con una sfera in testa all'arco: `ClockWidget.cycles`.
- Schedario componibile: le Impostazioni (pagina `new`, `widgets/new.py`; linguetta con
  ingranaggio e "impostazioni", disegnati da `folders.draw_tabs` al posto del nome, che resta "+"
  nei config) elencano solo i tipi opzionali (`new.tipi`, di norma timer e sveglia); ogni voce fa
  da interruttore, quindi una sola pagina per tipo. `App.add_page`/`remove_page` creano il widget e salvano `pages` in
  `config.local.json`; `App.page_kinds()` dice al widget cosa è già presente. Chiave della pagina
  `tipo` o `tipo#N`, sempre libera anche dopo una rimozione (più copie restano possibili da
  configurazione). La scheda resta ultima e non si può togliere.
- Tocco: bottoni individuali. Ogni modulo di pagina con bottoni espone `hits(box, widget, u)` →
  [(Box, id)] (registro `HITS`), usato da `draw` e da `CyberRenderer.hit_boxes`; `App.handle_tap`
  prova linguette, poi bottoni (un tocco entro `TAP_TOLERANCE` = 12 px vale per il più vicino),
  poi l'azione della pagina se `widget.tap_action`. Nelle Impostazioni il tocco fuori dai bottoni
  non fa nulla. Il punto grezzo è la mediana dei campioni fra appoggio e distacco, scartati il
  primo e gli ultimi due (sul resistivo sono i più sbagliati).
- Calibrazione a schermo: quattro croci al 10–12 % dai bordi, retta ai minimi quadrati per asse,
  scambio degli assi dalla correlazione più forte; rifiutata se la correlazione è < 0,9 o
  l'escursione < 300 unità grezze. `TouchCalibration.apply` la rende attiva senza riavvio; il
  risultato va in `config.local.json` (`save_local` unisce i dizionari in profondità).
- Luminosità (`dash/backlight.py`): LED vero da `/sys/class/backlight` se `max_brightness > 1`,
  altrimenti immagine scurita con una tabella (`Image.point`) prima di `display.show`. Nel
  simulatore sempre software, per non toccare lo schermo del PC. Livelli 10–100 a passi di 10.
- Alimentazione (`dash/power.py`): il Pi 3 dà solo sopra/sotto 4,63 V, non i volt. Si legge
  hwmon `rpi_volt` (nessun processo), in ripiego `vcgencmd get_throttled`; campione ogni
  `power.sample_s` (5 s) dentro `App.step`, storico di 48 colonne da un minuto (1 se nel minuto
  c'è stato un calo). Un calo conta quando comincia. Tensione bassa adesso → linguetta delle
  Impostazioni rosa con "tensione bassa", visibile da ogni pagina. Nel simulatore è spento.
- Spegnimento: doppio tocco entro 4 s; la schermata "spegnimento" arriva sul pannello prima del
  comando `power.cmd` (predefinito `sudo -n /usr/bin/systemctl poweroff`, permesso da
  `/etc/sudoers.d/pi-dash` e da nient'altro). Fuori dal driver `fb` è solo simulato.
- Meteo: direzione del vento come anello della home (`pages/weather._wind_ring` → `cv.ring`): arco
  da nord in senso orario fino alla direzione **da cui** soffia il vento (uso nautico), sfera in
  testa, gradi al centro, tacca sul nord. Niente aghi né radar. `cv.panel(reserve=...)` libera lo
  spazio a destra del numero.
- Rete: byte/s da `/proc/net/dev` (tutte le schede tranne `lo`), differenza fra due campioni;
  il primo campione dopo l'avvio vale None. Storico nel widget sistema, grafico in scala sul picco.
- Meteo: Open-Meteo (nessuna chiave), `wind_speed_unit=kn`, `timezone=auto`, 2 giorni orari;
  cache in `out/weather_cache.json`, contatore di versione per il ridisegno. Fase lunare calcolata
  localmente (mese sinodico medio).
- Posizione: `location.mode` = `auto` (predefinito: GPS da gpsd o NMEA, poi Wi-Fi con nmcli +
  BeaconDB, poi IP), `ip` (ipapi.co poi ip-api.com), `city` (geocoding Open-Meteo), `fixed`.
  L'IP da solo dava il nodo del provider (Lavinio invece di Gaeta). Con GPS e Wi-Fi il nome viene
  da Nominatim, altrimenti dal nome fisso se entro 10 km, altrimenti resta vuoto (mai il nome di
  un altro posto). `name/lat/lon` fanno da ripiego (Gaeta); cache in `out/location.json`,
  aggiornata ogni `refresh_h`, al ritmo del meteo. Cambio di posizione → dati meteo vecchi
  scartati.
- Alba/tramonto della Home: calcolo locale (funziona senza rete), nel fuso del sistema, quindi il
  Pi deve avere Europe/Rome. La pagina meteo usa i valori Open-Meteo.
- Timer: il tempo si compone con i bottoni: `presets_s` ordinati diventano "+N" che si sommano
  (anche in corsa, spostando la scadenza), "−1'" toglie un minuto senza scendere sotto zero, "C"
  azzera. Tocco sul pannello del tempo = avvia/pausa; B somma il preset più corto. All'avvio il
  primo preset con etichetta (`timer.labels`, 300 s → "PARTENZA"), altrimenti il primo. La barra
  si misura sul tempo impostato.
- Avvio: 5 s (la sigla "Pi-Dash" si scrive in circa 1,75 s); un tocco lo salta.
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
