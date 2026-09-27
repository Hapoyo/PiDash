# pi-dash — Installazione

Versione 0.5.2 · 2026-09-27

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
```
cd ~/pi-dash
.venv/bin/python -m dash -c config.json --touch-debug
```
Il dashboard compare sullo schermo. Ogni tocco scrive nel terminale
`tocco: grezzo x=… y=… → fx, fy`:
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
progetto, senza modificare i file del repository.
Controllo: `systemctl status pi-dash` deve dire `active (running)`; `q` per uscire.

Se il cursore o il login della console compaiono sopra il dashboard:
1. `sudo systemctl disable --now getty@tty1`
2. `sudo nano /boot/firmware/cmdline.txt`: il file ha **una sola riga**; vai in fondo (tasto Fine),
   aggiungi uno spazio e `vt.global_cursor_default=0`, senza andare a capo. Salva, esci,
   `sudo reboot`.

### 5.6 Comporre lo schedario: la scheda "+"
In partenza ci sono home, meteo, sistema e la scheda **+**. Timer e sveglia si aggiungono quando
servono: apri il **+**, scegli la voce e conferma.

| Con il tocco | Con i pulsanti |
|---|---|
| tocca una voce per sceglierla, poi il riquadro "+" in alto per confermare | B passa alla voce seguente, A conferma |

La stessa voce fa da interruttore: `+ timer` aggiunge la scheda, `− timer` la toglie. Lo schedario
risultante viene salvato in `config.local.json` (§ 5.7) e torna al riavvio; la scheda "+" resta
sempre l'ultima e non si può togliere.

Le schede elencate sono quelle di `new.tipi` (`timer`, `alarm`). Le pagine fisse — home, meteo,
sistema — stanno in `pages`: si cambiano dal file, non dal dashboard.

**Se vieni da una versione precedente** e il tuo `config.local.json` contiene `pages`, la scheda
"+" non compare: quell'elenco sostituisce quello del progetto. Due rimedi, a scelta:
1. togli tutto il blocco `pages` dal tuo `config.local.json` (`nano ~/pi-dash/config.local.json`):
   riprendi lo schedario del progetto e aggiungi timer e sveglia dal "+";
2. oppure aggiungi la scheda in fondo al tuo elenco: `{"name": "+", "widget": "new"}`.

Poi `sudo systemctl restart pi-dash`. Nel log (`journalctl -u pi-dash -n 20`) l'avviso lo ricorda.

### 5.7 Le tue impostazioni: `config.local.json`
`config.json` arriva da GitHub e viene sostituito a ogni aggiornamento. Le tue modifiche vanno in
`config.local.json`, nella stessa cartella: contiene **solo le voci da cambiare** e prevale su
`config.json`. Non è in Git, quindi gli aggiornamenti non lo toccano. Esempio:
```json
{
  "location": {"mode": "fixed", "name": "Gaeta", "lat": 41.213, "lon": 13.571},
  "alarm": {"alarms": [{"time": "06:30", "days": [0, 1, 2, 3, 4], "enabled": true}]},
  "input": {"touch": {"swap_xy": true, "invert_x": true}}
}
```
Le sezioni si fondono voce per voce; gli elenchi (`alarms`, `pages`, `presets_s`) si sostituiscono
per intero. Dopo una modifica: `sudo systemctl restart pi-dash`.

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
| Aggiungere o togliere una pagina | scheda "+" sul dashboard (§ 5.6) |
| Modificare le impostazioni | `nano ~/pi-dash/config.local.json`, poi riavviare il dashboard (§ 5.7) |
| Aggiornare dal repository | `~/pi-dash/scripts/aggiorna.sh` (§ 7) |
| Indirizzo IP | `hostname -I` |
| Temperatura del processore | `vcgencmd measure_temp` |
| Spazio libero | `df -h /` |
| Riavviare il Raspberry | `sudo reboot` |
| Spegnere il Raspberry | `sudo poweroff`, poi staccare quando il LED verde smette di lampeggiare |

Non staccare mai l'alimentazione senza `sudo poweroff`: si rischia di rovinare la microSD.

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
| Il Raspberry non compare nella rete | rete a 5 GHz (serve 2,4 GHz) o password Wi-Fi errata; prova con il cavo Ethernet e controlla il § 1 |
| Schermo 3,5" bianco | righe mancanti o scritte male in `config.txt` (§ 5.2) |
| `aggiorna.sh`: "ci sono file modificati a mano" | l'elenco dice quali; salva le modifiche che ti servono in `config.local.json`, poi `git checkout -- <file>` |
| Animazioni a scatti o processore caldo | abbassa `motion.fps` o usa `"livello": "eventi"` (§ 9.1) |
| Manca la scheda "+" dopo un aggiornamento | il tuo `config.local.json` contiene `pages`: § 5.6, in fondo |
| `aggiorna.sh`: "test falliti" o "configurazione non valida" | la versione precedente è già ripristinata; manda l'output a chi sviluppa |
| Schermo acceso ma dashboard assente | `sudo journalctl -u pi-dash -n 50` e leggi l'ultimo errore |
| Tocco nel punto sbagliato | calibrazione (§ 5.4) |
| Orario sbagliato | serve la rete all'avvio; controlla il fuso con `timedatectl` (deve dire Europe/Rome) |
| Blocchi o riavvii improvvisi, fulmine giallo sullo schermo | alimentatore insufficiente: usa 5,1 V 2,5 A |
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
