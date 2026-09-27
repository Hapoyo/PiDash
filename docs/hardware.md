# pi-dash — Note hardware

Versione 0.6.1 · 2026-09-27

## 1. Schermo 3,5" SPI
| Voce | Dato |
|---|---|
| Pannello | "3.5inch RPi Display" 480×320, controller ILI9486 |
| Touch | XPT2046 (compatibile ADS7846), resistivo |
| Overlay | `dtoverlay=piscreen,drm,speed=18000000` in `/boot/firmware/config.txt` |
| Pin usati (BCM) | SPI0: MOSI 10, MISO 9, SCLK 11, CE0 8 (display), CE1 7 (touch); DC 24, RST 25, IRQ touch 17, retroilluminazione 22 |
| Pin liberi | 27–40 (GPIO 5, 6, 13, 19, 26…) per pulsanti e cicalino |

- Lo schermo occupa i pin 1–26 del connettore: si innesta dal lato della microSD.
- Non usare gli script "LCD-show" del produttore: sostituiscono `config.txt` e i driver del kernel.
  L'overlay `piscreen` è già incluso in Raspberry Pi OS.
- Immagine capovolta: aggiungere `,rotate=90` alla riga `dtoverlay` (il valore predefinito è 270).
- Il touch va calibrato una volta: `--touch-debug`, poi `swap_xy`, `invert_x`, `invert_y` e gli
  estremi `x_min`/`x_max`/`y_min`/`y_max` in `config.json` (guida, § 5.4).

### 1.1 Banda del bus SPI e animazioni
| Voce | Valore |
|---|---|
| Schermo intero | 480 × 320 × 16 bit = 2 457 600 bit |
| Bus SPI (`speed=18000000`) | 18 Mbit/s → ~0,14 s per schermo intero, ~7 fotogrammi/s al massimo |
| Fascia di 16 righe | 480 × 16 × 16 bit = 122 880 bit → ~7 ms |

- Per questo `dash/display/fb.py` scrive solo le fasce di righe cambiate: gli effetti continui
  toccano zone piccole e restano fluidi a 8 fotogrammi/s; la scansione al cambio pagina riscrive
  lo schermo in 3–4 fotogrammi.
- L'aggiornamento parziale dipende dal driver DRM (`piscreen,drm`), che invia al pannello solo
  la zona scritta: da verificare sul Pi osservando fluidità e `top` durante le animazioni.
- Il progetto usa 18 MHz, sotto il valore predefinito dell'overlay `piscreen` (24 MHz,
  `spi-max-frequency` in `piscreen-overlay.dts`, fonte:
  [raspberrypi/linux](https://github.com/raspberrypi/linux/blob/rpi-6.12.y/arch/arm/boot/dts/overlays/piscreen-overlay.dts)).
  A 24 MHz uno schermo intero scende a ~0,10 s (~10 fotogrammi/s). Se si alza `speed`, farlo a
  passi e controllare che l'immagine resti pulita: in caso di disturbi tornare a 18 MHz.

### 1.2 Retroilluminazione
- Sul "3.5inch RPi Display" il LED è di norma collegato fisso: nessun `/sys/class/backlight`, oppure
  un dispositivo solo acceso/spento (`max_brightness` = 1). La luminosità delle Impostazioni
  scurisce allora l'immagine (`dash/backlight.py`, modo software).
- Se il pannello espone un dispositivo regolabile, il servizio lo rende scrivibile all'avvio
  (`ExecStartPre` in `systemd/pi-dash.service`) e il dashboard regola il LED vero.
- Prova: `ls /sys/class/backlight/ && cat /sys/class/backlight/*/max_brightness`.
- Il GPIO 22 non è un'uscita PWM hardware: un PWM software dal programma farebbe sfarfallare il
  pannello e contenderebbe il pin al driver, per questo non si usa.

## 2. Pulsanti e cicalino (opzionali)
- Pulsanti verso GND con pull-up interno: `input.gpio` = `{"next": 5, "action": 13, "back": 19}`.
- Cicalino: `input.buzzer_pin` su un GPIO libero (es. 26). Mai il 18, che alimenta lo schermo.

## 3. Raspberry Pi 3 Model B
- Alimentatore 5,1 V 2,5 A: sotto questa soglia il Pi si riavvia o rallenta (fulmine giallo).
- Nessun convertitore analogico: la tensione in ingresso non si misura in volt. Il firmware segnala
  solo quando scende sotto circa 4,63 V: hwmon `rpi_volt`, file `in0_lcrit_alarm` (1 = bassa
  adesso), oppure `vcgencmd get_throttled` (bit 0 adesso, bit 16 dall'accensione). Prova:
  `cat /sys/class/hwmon/hwmon*/name` deve elencare `rpi_volt`.
- Per i volt veri servirebbe un sensore esterno su I²C (per esempio INA219 fra alimentatore e Pi).
- Wi-Fi solo a 2,4 GHz.
- Nessun orologio interno: dopo un'accensione senza rete l'ora è sbagliata finché NTP non sincronizza.
- Il programma scrive direttamente nel framebuffer: non serve il desktop (Raspberry Pi OS Lite).
  L'utente del servizio deve stare nei gruppi `video`, `input` e `tty`.
- Nessun GPS. Dopo `systemctl poweroff` lo schermo SPI resta alimentato (e acceso) finché non si
  stacca l'alimentatore.

## 4. GPS (opzionale)
| Voce | Dato |
|---|---|
| Ricevitore consigliato | USB, chip u-blox 7/8 (compare come `/dev/ttyACM0`) |
| Software | `gpsd` (`sudo apt install -y gpsd gpsd-clients`), prova con `cgps` |
| Senza gpsd | lettura diretta NMEA (RMC/GGA) da `/dev/ttyACM0`, `/dev/ttyUSB0` o `location.gps_device` |
| Seriale sui pin (GPIO 14/15) | possibile (`location.gps_device`: `/dev/serial0`), ma va disattivata la console seriale in `raspi-config` |

- Il primo fix a freddo richiede da 30 s a qualche minuto con il cielo visibile; in casa può non
  arrivare mai. In quel caso vale la posizione dalle reti Wi-Fi.
