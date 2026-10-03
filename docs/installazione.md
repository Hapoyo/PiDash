# pi-dash — Installazione

Versione 0.9.1 · 2026-09-29

Guida passo passo per chi è nuovo del Raspberry Pi. Si lavora dal PC Windows: il Raspberry non
ha bisogno di monitor né di tastiera ("headless"). Le parti in `grassetto monospazio` si scrivono
esattamente così; `marinaio` e `dashboard` sono esempi di nome utente e nome del Raspberry.

## 0. Prima di iniziare

### 0.1 Materiale
| Voce | Dato |
|---|---|
| Scheda | Raspberry Pi 3 Model B |
| microSD | da 16 a 32 GB, classe A1 (va bene anche 8 GB) |
| Alimentatore | micro-USB 5,1 V 2,5 A (quello ufficiale del Pi 3); uno più debole causa blocchi |
| Lettore SD | nel PC o adattatore USB |
| Rete | Wi-Fi a 2,4 GHz (il Pi 3 Model B non vede le reti a 5 GHz) o cavo Ethernet |
| Schermo | 3,5" SPI 480×320, ILI9486 + touch XPT2046 |
| PC | Windows 10 o 11 |

### 0.2 Parole che incontrerai
| Termine | Significato |
|---|---|
| Terminale / PowerShell | finestra dove si scrivono i comandi; Invio li esegue |
| SSH | collegamento al terminale del Raspberry dal PC, attraverso la rete |
| `sudo` | esegue il comando come amministratore; può chiedere la password |
| `~` | la cartella personale sul Raspberry (`/home/marinaio`) |
| Prompt | la riga che aspetta un comando: `marinaio@dashboard:~ $` = sei sul Raspberry |
| `nano` | editor di testo nel terminale: frecce per muoversi, Ctrl+O e Invio salva, Ctrl+X esce |

Regole utili:
- Copia e incolla: in PowerShell il tasto destro del mouse incolla. Un comando alla volta.
- Le password nel terminale **non si vedono** mentre le scrivi: scrivile e premi Invio.
- Un comando andato bene di solito non scrive niente; le righe con `error` o `errore` vanno lette.
- Ctrl+C interrompe il programma in esecuzione.

## 1. Preparare la microSD
1. Sul PC scarica e installa **Raspberry Pi Imager** da raspberrypi.com/software.
2. Inserisci la microSD nel PC e apri Imager. Dalla versione 2.0 è una procedura a passi
   (Dispositivo → Sistema operativo → Archiviazione → Personalizzazione → Scrittura):
   1. **Dispositivo**: Raspberry Pi 3.
   2. **Sistema operativo**: Raspberry Pi OS (other) → **Raspberry Pi OS Lite (64-bit)**
      (senza desktop: il dashboard non ne ha bisogno ed è più leggero).
   3. **Archiviazione**: la microSD. Attenzione a non scegliere un altro disco.
3. **Personalizzazione** (da non saltare, serve per lavorare senza monitor):
   | Passo | Cosa inserire |
   |---|---|
   | Hostname | `dashboard` (solo lettere, cifre e trattino) |
   | Localizzazione | Roma: imposta da solo fuso orario Europe/Rome, tastiera e paese del Wi-Fi |
   | Utente | nome (es. `marinaio`) e password: **annotali**, non esiste più l'utente `pi` |
   | Wi-Fi | nome della rete (SSID, attenzione a maiuscole/minuscole) e password |
   | Accesso remoto | attiva **SSH** con autenticazione a password |
   | Raspberry Pi Connect | lascia spento |
4. Controlla il riepilogo, premi **Scrivi** e conferma: Imager scarica il sistema, lo scrive e lo
   verifica (10–20 minuti). Alla fine estrai la microSD.

## 2. Montare lo schermo
Sempre con il Raspberry **spento e senza alimentazione**.
Lo schermo si innesta sui primi 26 pin del connettore GPIO, dal lato della microSD, con il bordo
dello schermo allineato al bordo della scheda. Controlla che nessun pin resti scoperto a metà fila.

## 3. Primo avvio e collegamento dal PC
1. Inserisci la microSD nel Raspberry e collega l'alimentatore. Il primo avvio dura 2–3 minuti
   e può riavviarsi da solo una volta. Lo schermo 3,5" resta bianco: è normale finché non lo
   configuri (§ 5A).
2. Sul PC: Start → scrivi `PowerShell` → apri **Windows PowerShell**.
3. Collegati:
   ```
   ssh marinaio@dashboard.local
   ```
   - La prima volta chiede se fidarsi del dispositivo: scrivi `yes` e Invio.
   - Poi la password dell'utente (non si vede mentre scrivi).
   - Il prompt diventa `marinaio@dashboard:~ $`: da qui in poi i comandi girano sul Raspberry.
4. Aggiorna il sistema (5–15 minuti):
   ```
   sudo apt update && sudo apt full-upgrade -y
   sudo reboot
   ```
   Il riavvio chiude il collegamento: aspetta un minuto e ricollegati con il comando del punto 3.
5. Per uscire da SSH: `exit`.

Se `dashboard.local` non viene trovato: cerca l'indirizzo IP del Raspberry nella pagina del router
(dispositivi collegati, nome `dashboard`) e usa `ssh marinaio@192.168.1.23` (il tuo numero).

### 3.1 Cambiare rete Wi-Fi o password
Se il router cambia nome o password, o il Raspberry non si collega più, collegalo al router con il
cavo Ethernet, entra con SSH e lancia:

```
cd ~/pi-dash && .venv/bin/python -m dash --wifi
```

Mostra le reti visibili (quelle a 2,4 GHz vanno bene, quelle a 5 GHz no: il Pi 3 non le vede), chiede il
nome della rete (SSID, maiuscole comprese) e la password, **nascosta e da scrivere due volte**.
Poi aggiorna il profilo di quella rete, o lo crea, e si collega: alla fine scrive l'indirizzo IP.
Con `--wifi NOME` il nome è già dato. La password è tenuta da NetworkManager, non finisce in
`config.local.json`, nei log né su GitHub; se serve `sudo` ti chiede la password dell'utente.

La rete si salva anche quando non si vede ancora (router spento): il Pi si collega appena compare.
Se scrivi una password sbagliata il profilo resta salvato e il comando lo dice: rilancialo. Con
cavo e Wi-Fi insieme il cavo ha la precedenza: per provare il Wi-Fi davvero scollega il cavo, aspetta
30 secondi e collegati all'indirizzo che ti ha scritto (`hostname -I`). Il comando funziona anche se
`config.json` è rotto, perché non lo legge.

## 4. Trasferire il progetto dal PC al Raspberry
Il progetto arriva come `pi-dash.zip`. Supponiamo che sia nella cartella Download del PC.

### 4.1 Metodo A: da PowerShell (niente da installare)
1. Apri una **seconda** finestra PowerShell (non collegata al Raspberry) e scrivi:
   ```
   cd $HOME\Downloads
   scp .\pi-dash.zip marinaio@dashboard.local:~/
   ```
   Chiede la password del Raspberry, poi copia il file.
2. Nella finestra collegata al Raspberry:
   ```
   sudo apt install -y unzip
   unzip pi-dash.zip
   ls pi-dash
   ```
   L'ultimo comando deve elencare `CLAUDE.md`, `config.json`, `dash`, `docs`, `fonts`…

`scp` è già incluso in Windows 10 e 11. Se risponde "comando non riconosciuto": Impostazioni →
App → Funzionalità facoltative → Aggiungi → **Client OpenSSH**.

### 4.2 Metodo B: con finestre e trascinamento (WinSCP o FileZilla)
1. Installa **WinSCP** (winscp.net) e crea una connessione: protocollo **SFTP**, host
   `dashboard.local`, porta 22, nome utente e password del Raspberry.
2. Trascina `pi-dash.zip` nella cartella `/home/marinaio` a destra. Non nella radice `/`:
   lì scrivere è vietato e compare `Permission denied`.
3. Estrai dal terminale SSH come al punto 2 del metodo A.

### 4.3 Metodo C: direttamente da GitHub (consigliato)
Il Raspberry scarica il progetto da solo, senza passare dal PC. Nel terminale SSH:
```
sudo apt install -y git
git clone -b main https://github.com/Hapoyo/PiDash.git ~/pi-dash
ls ~/pi-dash
```
`-b main` scarica il ramo stabile, quello da cui arrivano gli aggiornamenti. Il progetto finisce in `~/pi-dash` qualunque sia il nome del repository. Se il repository è privato, `git clone`
chiede nome utente e **token** (non la password del sito): si crea su GitHub → Settings →
Developer settings → Personal access tokens.

## 5. Schermo 3,5" SPI (480×320, ILI9486, touch XPT2046)

### 5.1 Hardware
| Voce | Dato |
|---|---|
| Schermo | "3.5inch RPi Display" 480×320, controller ILI9486, touch resistivo XPT2046 (compatibile ADS7846) |
| Pin usati (BCM) | SPI0 (MOSI 10, MISO 9, SCLK 11, CE0 8 display, CE1 7 touch), DC 24, RST 25, IRQ touch 17, retroilluminazione 22 |
| Pin liberi | 27–40 (GPIO 5, 6, 13, 19, 26…) per pulsanti opzionali |

Non usare gli script "LCD-show" del produttore: sostituiscono `config.txt` e i driver. Il kernel di
Raspberry Pi OS ha già il driver (overlay `piscreen`).

### 5.2 Attivare lo schermo
1. Apri il file di configurazione di avvio:
   ```
   sudo nano /boot/firmware/config.txt
   ```
2. Vai in fondo con la freccia giù. Sotto l'ultima riga `[all]` aggiungi:
   ```
   dtparam=spi=on
   dtoverlay=piscreen,drm,speed=18000000
   ```
3. Salva (Ctrl+O, Invio) ed esci (Ctrl+X), poi `sudo reboot`.
4. Dopo il riavvio lo schermo mostra le scritte di avvio. Ricollegati e verifica:
   ```
   cat /sys/class/graphics/fb*/name
   grep -A4 ADS7846 /proc/bus/input/devices
   ```
   Il primo deve contenere `ili9486`, il secondo una riga `Handlers=… eventN`.
   Immagine capovolta: nella riga `dtoverlay` aggiungi `,rotate=90` (il predefinito è 270).

### 5.3 Installare il programma
```
sudo apt install -y python3-venv python3-pil
cd ~/pi-dash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
```
`.venv` è un ambiente Python dedicato al progetto: non tocca il Python del sistema.

### 5.4 Prova e calibrazione del tocco
Il modo più semplice è dallo schermo: **Impostazioni** (la linguetta con l'ingranaggio) →
**calibra touch**, poi tocca il centro delle quattro croci arancio, una alla volta. Estremi,
scambio e inversione degli assi vengono calcolati, applicati subito e salvati in
`config.local.json` (§ 5.7). Se i tocchi non sono coerenti compare "calibrazione non riuscita":
basta ripetere. Senza tocchi la calibrazione si annulla da sola dopo 30 s.

Se il tocco è così storto da non riuscire a premere "calibra touch", c'è la procedura a mano:
```
cd ~/pi-dash
.venv/bin/python -m dash -c config.json --touch-debug
```
Il dashboard compare sullo schermo. Ogni tocco scrive nel terminale
`tocco: grezzo x=… y=… (N campioni) → fx, fy`:
1. Tocca l'angolo in alto a sinistra: deve dare circa `0.0, 0.0`; in basso a destra circa `1.0, 1.0`.
2. Assi scambiati → `"swap_xy": true`; destra/sinistra al contrario → `"invert_x": true`;
   alto/basso al contrario → `"invert_y": true`. Si modificano con
   `nano config.local.json`, nella sezione `input` → `touch` (vedi § 5.7).
3. Se i bordi non arrivano a 0/1: annota i valori grezzi minimi e massimi agli angoli e
   scrivili in `x_min`, `x_max`, `y_min`, `y_max`.
4. Ctrl+C per fermare, correggi, riprova.

### 5.5 Avvio automatico all'accensione
```
cd ~/pi-dash
scripts/installa-servizio.sh
sudo systemctl start pi-dash
```
Lo script scrive in `/etc/systemd/system/pi-dash.service` il tuo nome utente e la cartella del
progetto, senza modificare i file del repository. Installa anche `/etc/sudoers.d/pi-dash`, che
permette al dashboard un solo comando da amministratore, `systemctl poweroff`, per il bottone
"spegni" delle Impostazioni.
Controllo: `systemctl status pi-dash` deve dire `active (running)`; `q` per uscire.

Se il cursore o il login della console compaiono sopra il dashboard:
1. `sudo systemctl disable --now getty@tty1`
2. `sudo nano /boot/firmware/cmdline.txt`: il file ha **una sola riga**; vai in fondo (tasto Fine),
   aggiungi uno spazio e `vt.global_cursor_default=0`, senza andare a capo. Salva, esci,
   `sudo reboot`.

### 5.6 Le Impostazioni: schede, luminosità, spegnimento
In partenza ci sono home, meteo, sistema e le **Impostazioni** (linguetta con l'ingranaggio,
l'ultima). Dentro, tre righe:

| Riga | Cosa fa |
|---|---|
| schede | `+ timer`, `+ sveglia`: un tocco aggiunge la scheda; la stessa voce diventa `− timer` e la toglie |
| luminosità | `−` e `+` dal 10 al 100 %, a passi di 10 |
| sistema | `calibra touch` (§ 5.4) e `spegni`: al primo tocco diventa "conferma", al secondo (entro 4 s) spegne il Raspberry |
| tensione | grafico degli ultimi 48 minuti, una colonna al minuto: grigia se l'alimentazione è rimasta sopra 4,63 V, rosa se è scesa sotto |

Con i pulsanti GPIO: B passa alla scheda seguente dell'elenco, A la aggiunge o la toglie.

Lo schedario e la luminosità vengono salvati in `config.local.json` (§ 5.7) e tornano al
riavvio; le Impostazioni restano sempre l'ultima scheda e non si possono togliere.

**Luminosità.** Se il pannello espone la retroilluminazione (`ls /sys/class/backlight` non è
vuoto e `max_brightness` è più di 1) si regola il LED vero; sulla maggior parte degli schermi
3,5" il LED è collegato fisso, e allora il dashboard scurisce l'immagine. In fondo alle
Impostazioni c'è scritto quale dei due modi è in uso ("retroilluminazione" o "luce software").

**Spegnimento.** Compare la schermata "spegnimento": dopo circa 20 s, quando il LED verde del
Raspberry smette di lampeggiare, si può staccare l'alimentatore. Lo schermo 3,5" resta acceso
anche a Raspberry spento (prende corrente dal connettore): è normale. Lo spegnimento dallo
schermo richiede la regola installata da `scripts/installa-servizio.sh` (§ 5.5); se manca, in
fondo alle Impostazioni compare "spegni non consentito".

**Tensione di alimentazione.** Il Raspberry Pi 3 non misura i volt in ingresso, ma il suo
rilevatore di sottotensione scatta quando scendono sotto circa 4,63 V (il "fulmine giallo"). Il
dashboard lo legge ogni 5 s. A destra del grafico:

| Scritta | Significato |
|---|---|
| `ok ≥ 4,63 V` | nessun calo da quando il dashboard è partito |
| `cali 2 · 07:31` (ambra) | la tensione è scesa sotto soglia 2 volte, l'ultima alle 07:31 |
| `sotto 4,63 V` (rosa, riquadro che lampeggia) | la tensione è bassa adesso |
| `non misurabile qui` | nel simulatore sul PC |

Mentre la tensione è bassa, la linguetta delle Impostazioni diventa rosa con scritto
"tensione bassa", ed è visibile da ogni pagina. Rimedio: alimentatore da 5,1 V 2,5 A e cavo
corto e spesso (i cavi sottili perdono tensione sotto carico).

Le schede elencate sono quelle di `new.tipi` (`timer`, `alarm`). Le pagine fisse — home, meteo,
sistema — stanno in `pages`: si cambiano dal file, non dal dashboard.

**Se vieni da una versione precedente** e il tuo `config.local.json` contiene `pages`, le
Impostazioni non compaiono: quell'elenco sostituisce quello del progetto. Due rimedi, a scelta:
1. togli tutto il blocco `pages` dal tuo `config.local.json` (`nano ~/pi-dash/config.local.json`):
   riprendi lo schedario del progetto e aggiungi timer e sveglia dalle Impostazioni;
2. oppure aggiungi la scheda in fondo al tuo elenco: `{"name": "+", "widget": "new"}`.

Poi `sudo systemctl restart pi-dash`. Nel log (`journalctl -u pi-dash -n 20`) l'avviso lo ricorda.

### 5.7 Le tue impostazioni: `config.local.json`
`config.json` arriva da GitHub e viene sostituito a ogni aggiornamento. Le tue modifiche vanno in
`config.local.json`, nella stessa cartella: contiene **solo le voci da cambiare** e prevale su
`config.json`. Non è in Git, quindi gli aggiornamenti non lo toccano. Esempio:
```json
{
  "location": {"mode": "fixed", "name": "Ventotene", "lat": 40.796, "lon": 13.436},
  "alarm": {"alarms": [{"time": "06:30", "days": [0, 1, 2, 3, 4], "enabled": true}]},
  "input": {"touch": {"swap_xy": true, "invert_x": true}}
}
```
Le sezioni si fondono voce per voce; gli elenchi (`alarms`, `pages`, `presets_s`) si sostituiscono
per intero. Dopo una modifica: `sudo systemctl restart pi-dash`. Calibrazione del touch,
schedario e luminosità ci finiscono da soli quando li cambi dalle Impostazioni.

### 5.8 Posizione: GPS, Wi-Fi, IP
Con `"mode": "auto"` (quella del progetto) il dashboard prova, in ordine:
1. **GPS**, se c'è un ricevitore: tramite `gpsd` o leggendo direttamente la seriale
   (`/dev/ttyACM0`, `/dev/ttyUSB0`, oppure quella in `location.gps_device`);
2. **reti Wi-Fi vicine**: l'elenco delle reti visibili (`nmcli`) va a
   [BeaconDB](https://beacondb.net), che restituisce la posizione con la precisione di una via.
   Vengono inviati gli identificativi (BSSID) delle reti vicine, non il loro traffico; per non
   usarlo: `"location": {"wifi": false}`;
3. **indirizzo IP**: solo a livello di città, e spesso indica il nodo del provider, non il paese
   vero (per esempio Lavinio invece di Gaeta);
4. le coordinate fisse `name`/`lat`/`lon` (nel progetto: Gaeta).

La home mostra accanto alle coordinate da dove arriva la posizione: `gps`, `wifi` o `ip`. La
posizione si aggiorna insieme al meteo, al più ogni `refresh_h` ore.

Il Raspberry Pi 3 non ha un GPS. Per aggiungerlo basta un ricevitore USB (per esempio con
chip u-blox 7 o 8, 10–15 €):
```
sudo apt install -y gpsd gpsd-clients
cgps     # deve comparire un fix con latitudine e longitudine (serve il cielo aperto)
```
Se non vuoi nessuna ricerca automatica: `"location": {"mode": "fixed"}` in `config.local.json`.

### 5.9 Needle: modello locale per function calling
[Needle](https://github.com/cactus-compute/needle) è un modello da 35 MB che trasforma una frase
("timer 5 minuti") nella chiamata a una funzione (`start_timer_minutes(minutes=5)`). Non è un chatbot: gira
sul Raspberry Pi 3 in circa 2 s a frase, con 75 MB di RAM e senza rete. Le funzioni che conosce
sono in `needle/tools.json`. Il servizio ascolta solo su `127.0.0.1:8090`: non è raggiungibile
dalla rete locale.

1. Scarica il runtime e il modello per Raspberry (ARM 64 bit), una volta sola:
   ```
   python3 -m venv ~/needle-env && ~/needle-env/bin/pip install cactus-needle
   ~/needle-env/bin/needle download linux-arm64 --out ~/needle
   ```
2. Installa e avvia il servizio, come per il dashboard:
   ```
   ~/pi-dash/scripts/installa-needle.sh ~/needle
   ```
   Lo script scrive `/etc/systemd/system/needle.service` con il tuo utente e le cartelle vere,
   abilita l'avvio automatico e riavvia il servizio. Limite di memoria: 300 MB.
3. Prova: `curl -s -X POST localhost:8090/complete -d '{"input":"timer 5 minuti"}'` risponde con
   `function_calls`, `confidence` e i tempi. Controllo: `systemctl status needle`.
4. Nelle Impostazioni tocca `+ needle`: compare la scheda **Needle**, con lo stato del servizio
   (pronto, penso…, offline) e quattro bottoni, uno per frase di `needle.queries`. Il tocco invia
   la frase, la esegue (vedi sotto) e scrive in alto cosa ha fatto; il bot ne mostra l'esito. Con i
   pulsanti GPIO: B sceglie la frase, A la invia.

**Cosa fa il dashboard con la risposta.** Se la confidenza è sufficiente la funzione riconosciuta
viene eseguita, e in alto nella scheda compare cosa è successo (`→ timer 5' avviato`). La soglia
dipende dal danno di un errore: 0,6 (`needle.soglia`) per timer e sveglia, che cambiano qualcosa;
0,35 (`needle.soglia_pagine`) per le funzioni che aprono soltanto una pagina, dove sbagliare costa
un tocco sulla linguetta giusta; 0,4 (`needle.soglia_luci`) per le luci, che hanno in più i
controlli del § 5.10. Sotto soglia la scheda scrive "confidenza bassa: non eseguo".

| Funzione | Effetto |
|---|---|
| `start_timer_minutes(minutes)`, `start_timer_seconds(seconds)` | imposta il timer e lo avvia (da 1 s a 180′), sostituendo il tempo in corso; se la pagina Timer non c'è la crea |
| `set_alarm(time)` | sveglia `HH:MM` **ogni giorno**, salvata in `config.local.json`; la stessa ora non si duplica, al massimo 10; se la pagina Sveglia non c'è la crea |
| `open_home`, `open_weather`, `open_timer`, `open_alarm`, `open_system`, `open_settings` | apre quella pagina, se c'è |
| `get_weather(city)` | apre il meteo del luogo del dashboard (altre città non ancora) |
| `lights_on(room)`, `lights_off(room)`, `set_brightness(room, percent)` | luci Philips Hue di una stanza o di tutta la casa: § 5.10 |

Il modello è piccolo (35 MB): copia i numeri della frase senza convertire le unità e capisce
l'italiano solo in parte. Per questo ci sono due funzioni per il timer (minuti e secondi) e una
per pagina, e per questo esiste la soglia: con "timer di 90 secondi" una sola `start_timer(minutes)`
avviava 90 minuti. Le frasi che funzionano meglio sono quelle semplici ("timer 5 minuti", "timer
di 90 secondi", "svegliami alle 6:45", "vai alla home", "apri la pagina sistema"); una frase
incerta non viene eseguita e la scheda lo dice. Dopo un riavvio del servizio (o di `aggiorna.sh`
quando cambiano le funzioni) la scheda resta "offline" per circa 30 secondi: il modello sta partendo.

Non esiste nessuna funzione per spegnere il Raspberry: il modello propone, ma il dashboard esegue
solo questo elenco, controllando gli argomenti. Con `needle.naviga: false` le azioni si eseguono
senza cambiare pagina; con `needle.esegui: false` la scheda torna a mostrare e basta. Le sveglie
create così non si tolgono dallo schermo: si modificano in `config.local.json`.

Per cambiare frasi o indirizzo: sezione `needle` di `config.local.json` (§ 5.7). Per cambiare le
funzioni: `needle/tools.json` (e `dash/azioni.py` per eseguirle), poi
`sudo systemctl restart needle`. Adattare il modello alle proprie frasi (`needle finetune`) si
fa su un PC, non sul Pi.

### 5.10 Luci Philips Hue con Needle
Dopo `+ needle` (§ 5.9) il dashboard può accendere, spegnere e regolare le luci del bridge Hue
nella rete di casa: "accendi il soggiorno", "spegni tutte le luci", "soppalco al 30 per cento".
Il modello dice quale stanza; il bridge risponde in meno di un secondo.

1. **Registra PiDash sul bridge**, una volta sola. Sul Raspberry:
   ```
   cd ~/pi-dash && .venv/bin/python -m dash --hue-registra
   ```
   Premi il grande tasto rotondo del bridge entro 30 secondi. Senza indirizzo cerca il bridge
   tramite `discovery.meethue.com` (il servizio di Signify vede il tuo IP pubblico); per evitarlo:
   `--hue-registra 192.168.1.73`. La chiave va in `config.local.json`, che resta a permessi 600,
   e non viene mai stampata: non è in `config.json`, quindi non finisce su GitHub.
2. Aggiorna il dashboard e il modello: `~/pi-dash/scripts/aggiorna.sh` (le funzioni delle luci
   sono in `needle/tools.json`).
3. Aggiungi le frasi alla scheda, in `config.local.json`, per esempio
   `"needle": {"queries": ["accendi il soggiorno", "spegni tutte le luci", ...]}` (da 1 a 6).

**Come si riconoscono le stanze.** Il nome detto viene confrontato con le stanze del bridge senza
accenti né articoli ("la luce del Soppalco" → Soppalco). Se due stanze potrebbero andare bene
("gaeta" per "Corridoio Gaeta" e "Camera Gaeta") non si indovina: la scheda scrive "stanza
ambigua". "tutte", "casa" o nessuna stanza vogliono dire tutte le luci. Se le luci della stanza
non rispondono (spente dall'interruttore) l'esito dice "(non raggiungibili)".

**Controlli di sicurezza.** Il modello piccolo scambia "accendi" con "spegni" (con "accendi tutte
le luci" ha risposto `lights_off`) e inventa i numeri. Per questo il dashboard non si fida di lui
su queste due cose:
- **accendere o spegnere lo decide il verbo della frase** (accendi, attiva · spegni, disattiva):
  se manca, se ce ne sono di opposti o se c'è una negazione ("non accendere") non si esegue;
- **la luminosità deve essere scritta nella frase**: "al 50 per cento" va, "abbassa" no.

**Accendere a un livello.** Una frase che accende e dice anche il livello, come "accendi il
soggiorno al 100%", "…al 100 per cento" o "…al massimo", accende la stanza a quella
luminosità. Il livello lo legge il dashboard dal testo (il modello, con quella frase, risponde
`lights_off` e lo perderebbe). Da 1 a 100: fuori scala non si esegue. Spegnendo il livello è
ignorato; senza livello "accendi il soggiorno" mantiene la luminosità di prima.

Con "accendi tutte le luci" si accende davvero tutta la casa: la frase è proprio quella che dici.
Il bridge è raggiunto in HTTPS senza verificare il certificato (è autofirmato) e solo sulla rete
locale; se il bridge è spento il dashboard rallenta di `hue.timeout_s` (2 s) e lo dice.

### 5.11 Frasi, timer, sveglie e azioni personalizzate
Il modello da 35 MB sbaglia i numeri e le unità, quindi per timer, sveglie e luci il dashboard ha un
**interprete di frasi in italiano** (`dash/frasi.py`) che decide da solo, senza aspettare i 2 secondi
del modello e senza sbagliare. Quello che non riconosce con certezza va al modello come prima
(meteo, apri una pagina…). Funziona anche con il servizio Needle spento. Per disattivarlo:
`"needle": {"regole": false}`.

| Dici | Succede |
|---|---|
| "timer 5 minuti", "timer di 90 secondi", "timer 1h 15min", "timer un'ora e mezza", "timer 1 ora e 30", "timer mezz'ora", "timer un quarto d'ora", "timer due minuti e mezzo", "timer venticinque minuti", "avvisami tra dieci minuti" | timer di quella durata, avviato (da 1 s a 180′) |
| "ferma il timer", "metti in pausa il timer", "riprendi il timer" | ferma (torna al tempo impostato), pausa, riprende |
| "svegliami alle 7", "alle 7:30", "alle sette e mezza", "alle 7 e un quarto", "alle 8 meno un quarto", "alle 9 di sera", "all'una", "a mezzogiorno" | sveglia a quell'ora, ogni giorno |
| "… dal lunedì al venerdì", "… nei giorni feriali", "… nel weekend", "… sabato e domenica", "… il lunedì e il giovedì" | la stessa sveglia solo in quei giorni |
| "cancella la sveglia delle 7", "cancella tutte le sveglie" | toglie quella sveglia, o tutte solo se lo dici ("cancella la sveglia" da sola non fa nulla) |
| "accendi il soggiorno", "spegni tutte le luci", "soggiorno al 50", "soggiorno a metà", "corridoio al massimo" | accende, spegne, regola (§ 5.10) |
| "luce rossa in terrazza", "soggiorno azzurro" | colore: rosso, arancione, giallo, verde, azzurro, blu, viola, rosa |
| "luce calda in soggiorno", "luce fredda", "luce naturale", "luce bianca" | temperatura del bianco |
| "alza la luce del corridoio", "abbassa il soggiorno", "abbassa il soggiorno di 30 percento" | più o meno luminosa di 20 punti (o di quanto dici) rispetto a com'è ora |

Una frase con sveglia o timer che non si capisce non passa alle luci ("spegni la sveglia" non
spegne una stanza). Con una negazione ("non accendere") non si esegue. Una stanza che non c'è dà
"stanza sconosciuta: cucina"; senza stanza ("accendi la luce") la scheda chiede "di quale stanza?":
non si accende mai tutta la casa per un equivoco. Cambiare colore o luminosità accende le luci;
spegnendo, il resto della frase è ignorato.

**Azioni personalizzate.** In `config.local.json`, sezione `needle`, `azioni` è una lista (fino a 30
voci) di comandi che scegli tu e richiami con una parola. Ogni voce ha un `nome`, le `frasi` che la
attivano (basta che la parola compaia nella frase: vince la più lunga) e, da sole o insieme, queste
azioni, eseguite nell'ordine timer, sveglia, luci, pagina:

```json
"needle": {
  "azioni": [
    {"nome": "pasta", "frasi": ["pasta", "spaghetti"], "timer": {"minuti": 9}},
    {"nome": "buonanotte", "frasi": ["buonanotte", "vado a dormire"],
     "sveglia": "07:00", "giorni": [0, 1, 2, 3, 4],
     "luci": [{"stanza": "tutte", "acceso": false}], "pagina": "alarm"},
    {"nome": "cinema", "frasi": ["cinema", "film"],
     "luci": [{"stanza": "soggiorno", "percentuale": 15, "temperatura": "calda"},
              {"stanza": "corridoio", "acceso": false}]}
  ]
}
```
- `timer`: `ore`, `minuti`, `secondi` (interi, da 1 s a 180′);
- `sveglia`: `"HH:MM"`, con `giorni` (0 = lunedì … 6 = domenica; senza, ogni giorno);
- `luci`: elenco di comandi con `stanza` ("tutte" per casa) e, a scelta, `acceso` (true/false),
  `percentuale` (1–100), `colore` (rosso, arancione, giallo, verde, azzurro, blu, viola, rosa)
  oppure `temperatura` (fredda, bianca, naturale, calda), non insieme;
- `pagina`: home, weather, timer, alarm, system, settings.

Una voce sbagliata (colore che non esiste, ora 25:00…) ferma il dashboard all'avvio con un messaggio
che dice quale voce e cosa correggere; il file resta com'è. Per usarle bisogna dire la frase: aggiungila
a `needle.queries` (i bottoni della scheda, da 1 a 6; con B scegli e con A invii). Una voce con più
azioni le esegue una dopo l'altra: l'esito le riassume (troncato a 40 caratteri) e se un passo fallisce
(bridge spento) gli altri partono comunque.

### 5.12 Il bot di Needle
Sulla scheda Needle una testa di robot mostra cosa sta facendo il modello. Con `motion.livello`
`pieno` si muove; con `eventi` o `off` resta ferma ma cambia faccia.

| Faccia | Quando |
|---|---|
| zzz, occhi chiusi, antenna spenta | servizio spento (`systemctl start needle`), a meno che la frase sia una che l'interprete capisce da solo |
| occhi stretti che scorrono | controllo se il servizio è acceso (primi secondi) |
| occhi aperti che sbattono, antenna che pulsa | pronto |
| occhi in alto, tre puntini, antenna che lampeggia, fondo arancio | sta pensando (richiesta in corso) |
| occhi sorridenti e sorriso, saltello | frase eseguita |
| un occhio grande, sopracciglio, "?" | nessuna funzione riconosciuta o confidenza troppo bassa |
| occhi a croce rosa, bocca a zig-zag, scossa | errore (servizio che non risponde, bridge Hue spento, argomento rifiutato) |

Dopo una risposta la faccia dell'esito dura 6 secondi, poi il bot torna "pronto".

## 6. Comandi di tutti i giorni
Nome del servizio: `pi-dash`.

| Cosa | Comando |
|---|---|
| Stato del dashboard | `systemctl status pi-dash` (q per uscire) |
| Messaggi in diretta | `sudo journalctl -u pi-dash -f` (Ctrl+C per uscire) |
| Ultimi 50 messaggi | `sudo journalctl -u pi-dash -n 50` |
| Riavviare il dashboard | `sudo systemctl restart pi-dash` |
| Fermarlo (per le prove a mano) | `sudo systemctl stop pi-dash` |
| Non avviarlo più all'accensione | `sudo systemctl disable pi-dash` |
| Aggiungere o togliere una pagina | Impostazioni sul dashboard (§ 5.6) |
| Luminosità, calibrazione, spegnimento | Impostazioni sul dashboard (§ 5.6) |
| Modificare le impostazioni | `nano ~/pi-dash/config.local.json`, poi riavviare il dashboard (§ 5.7) |
| Cambiare rete Wi-Fi o password | `cd ~/pi-dash && .venv/bin/python -m dash --wifi` (§ 3.1) |
| Aggiornare dal repository | `~/pi-dash/scripts/aggiorna.sh` (§ 7) |
| Indirizzo IP | `hostname -I` |
| Temperatura del processore | `vcgencmd measure_temp` |
| Spazio libero | `df -h /` |
| Riavviare il Raspberry | `sudo reboot` |
| Spegnere il Raspberry | Impostazioni → spegni → conferma, oppure `sudo poweroff`; poi staccare quando il LED verde smette di lampeggiare |

Non staccare mai l'alimentazione senza spegnere prima: si rischia di rovinare la microSD.

## 7. Aggiornare il programma a una nuova versione
Se hai installato da GitHub (§ 4.3), un solo comando:
```
~/pi-dash/scripts/aggiorna.sh
```
Lo script:
1. controlla i file modificati a mano. Se hai cambiato `config.json` sposta le modifiche in
   `config.local.json` (§ 5.7); se hai il file del servizio modificato col vecchio metodo lo ripristina;
2. scarica da GitHub (`git pull`) il ramo in uso, di solito `main`, ed elenca le novità;
3. aggiorna le dipendenze se `requirements.txt` è cambiato;
4. esegue i test e verifica che la tua configurazione sia ancora valida: se qualcosa non va
   **torna da solo alla versione precedente** e lascia il dashboard com'era;
5. reinstalla il servizio se il suo file è cambiato, poi riavvia `pi-dash`.

Chiede la password di `sudo` solo per il riavvio. Con `--no-test` salta i test (più veloce).
Se non c'è niente di nuovo scrive "già all'ultima versione" e non riavvia nulla.

Aggiornamento dal PC, senza aprire una sessione SSH:
```
ssh marinaio@dashboard.local ~/pi-dash/scripts/aggiorna.sh
```

### 7.1 Passare dallo zip (o dalla copia dal PC) a GitHub
Una volta sola, poi si aggiorna con `aggiorna.sh`. Le tue impostazioni diventano `config.local.json`:
```
sudo systemctl stop pi-dash
mv ~/pi-dash ~/pi-dash-vecchio
git clone -b main https://github.com/Hapoyo/PiDash.git ~/pi-dash
cp ~/pi-dash-vecchio/config.json ~/pi-dash/config.local.json
cd ~/pi-dash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
scripts/installa-servizio.sh
sudo systemctl start pi-dash
```
Se tutto funziona: `rm -rf ~/pi-dash-vecchio`.

### 7.2 Aggiornare dallo zip
Se continui a installare dallo zip:
1. Copia il nuovo `pi-dash.zip` sul Raspberry come al § 4.
2. Sul Raspberry:
   ```
   sudo systemctl stop pi-dash
   unzip -o pi-dash.zip
   cd ~/pi-dash && .venv/bin/pip install -r requirements.txt
   sudo systemctl start pi-dash
   ```
   `-o` sovrascrive i file senza chiedere; `.venv` resta com'è.
3. `config.json` viene sovrascritto; `config.local.json` (§ 5.7) non è nello zip e resta com'è.

## 8. Problemi comuni
| Sintomo | Causa probabile e rimedio |
|---|---|
| `Could not resolve hostname dashboard.local` | usa l'indirizzo IP (§ 3); aspetta 2–3 minuti dopo l'accensione |
| `Permission denied, please try again` | nome utente o password errati: sono quelli scelti in Imager |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` dopo aver riscritto la microSD | sul PC: `ssh-keygen -R dashboard.local`, poi ricollegati |
| Il Raspberry non compare nella rete | rete a 5 GHz (serve 2,4 GHz) o password Wi-Fi errata; collegalo con il cavo Ethernet, poi `python -m dash --wifi` (§ 3.1) |
| Schermo 3,5" bianco | righe mancanti o scritte male in `config.txt` (§ 5.2) |
| `aggiorna.sh`: "ci sono file modificati a mano" | l'elenco dice quali; salva le modifiche che ti servono in `config.local.json`, poi `git checkout -- <file>` |
| Animazioni a scatti o processore caldo | abbassa `motion.fps` o usa `"livello": "eventi"` (§ 9.1) |
| Mancano le Impostazioni dopo un aggiornamento | il tuo `config.local.json` contiene `pages`: § 5.6, in fondo |
| `aggiorna.sh`: "test falliti" o "configurazione non valida" | la versione precedente è già ripristinata; manda l'output a chi sviluppa |
| Schermo acceso ma dashboard assente | `sudo journalctl -u pi-dash -n 50` e leggi l'ultimo errore |
| Tocco nel punto sbagliato | Impostazioni → calibra touch (§ 5.4) |
| Scheda Needle "offline" | `systemctl status needle`; se manca, `scripts/installa-needle.sh` (§ 5.9); log: `sudo journalctl -u needle -n 50` |
| "spegni non consentito" | lancia `scripts/installa-servizio.sh` (installa la regola per lo spegnimento) |
| Località sbagliata (es. Lavinio invece di Gaeta) | posizione da IP: § 5.8 (Wi-Fi, GPS o coordinate fisse) |
| Orario sbagliato | serve la rete all'avvio; controlla il fuso con `timedatectl` (deve dire Europe/Rome) |
| Blocchi o riavvii improvvisi, fulmine giallo, "tensione bassa" sulla linguetta | alimentatore o cavo insufficiente: usa 5,1 V 2,5 A e un cavo corto (§ 5.6) |
| `unzip: command not found` | `sudo apt install -y unzip` |

## 9. Aspetto

### 9.1 Animazioni
In `config.local.json`, sezione `motion`:

| Voce | Valori | Effetto |
|---|---|---|
| `livello` | `"pieno"` (predefinito) | accensione, scansione al cambio pagina, cifre che si decodificano, più effetti continui (radar, aloni, spie, due punti) |
| | `"eventi"` | solo le animazioni brevi legate a un evento: lo schermo resta fermo il resto del tempo |
| | `"off"` | nessuna animazione |
| `fps` | 1–30, predefinito `8` | fotogrammi al secondo delle animazioni |
| `avvio` | `true` / `false` | sequenza di accensione (un tocco la salta) |

Esempio: `{"motion": {"livello": "eventi"}}`. Poi `sudo systemctl restart pi-dash`.

Se il Raspberry scalda o le animazioni scattano, prova `"fps": 5` oppure `"livello": "eventi"`.
Temperatura: `vcgencmd measure_temp` (sopra 80 °C il processore rallenta da solo).

### 9.2 Colori
I colori si cambiano in `config.local.json` (§ 5.7), sezione `theme` → `palette`: si indicano solo le voci da
sostituire, in formato `#rrggbb`.

| Voce | Uso |
|---|---|
| `bg` | fondo dello schermo |
| `panel` | cartella aperta e riquadri scuri |
| `cream` | linguette chiuse e testo chiaro |
| `paper` | crema più chiaro (riquadro di allarme) |
| `tan` | grigio caldo (etichette, pannello disco) |
| `orange` `amber` `pink` | pannelli in evidenza (vento, pressione, pioggia, pagina attiva) |
| `ink` | testo scuro sui pannelli chiari |
| `line` | linee sottili e bordi delle linguette chiuse |

Esempio:
```json
"theme": { "palette": { "pink": "#d64550", "amber": "#e8b04b" } }
```
