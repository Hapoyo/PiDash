# pi-dash — Note hardware

Versione 0.1.0 · 2026-09-25

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

## 2. Pulsanti e cicalino (opzionali)
- Pulsanti verso GND con pull-up interno: `input.gpio` = `{"next": 5, "action": 13, "back": 19}`.
- Cicalino: `input.buzzer_pin` su un GPIO libero (es. 26). Mai il 18, che alimenta lo schermo.

## 3. Raspberry Pi 3 Model B
- Alimentatore 5,1 V 2,5 A: sotto questa soglia il Pi si riavvia o rallenta (fulmine giallo).
- Wi-Fi solo a 2,4 GHz.
- Nessun orologio interno: dopo un'accensione senza rete l'ora è sbagliata finché NTP non sincronizza.
- Il programma scrive direttamente nel framebuffer: non serve il desktop (Raspberry Pi OS Lite).
  L'utente del servizio deve stare nei gruppi `video`, `input` e `tty`.
