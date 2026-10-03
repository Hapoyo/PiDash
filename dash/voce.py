"""Voce dal telefono: pagina web "premi e parla" servita dal Pi.

Il telefono riconosce la voce nel browser (Web Speech API, italiano) e manda a pi-dash solo il
testo: la frase arriva a Needle come se fosse stata toccata sullo schermo, con le stesse regole,
soglie e azioni. I browser danno il microfono solo alle pagine HTTPS, quindi il server parla TLS:
certificato indicato in `voce.cert`/`voce.key` (Tailscale, o uno proprio) oppure, se mancano,
un certificato autofirmato creato con `openssl` in `out/voce/`. Senza openssl resta in HTTP: la
pagina funziona lo stesso con il microfono della tastiera del telefono.

Il server non tocca il dashboard: mette `Frase` nella coda degli eventi (la esegue `App.step`)
e risponde allo stato con `App.voce_stato`, che legge solo dati protetti da lock.
"""
from __future__ import annotations

import hmac
import json
import logging
import queue
import socket
import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, NamedTuple
from urllib.parse import parse_qs, quote, urlsplit

log = logging.getLogger(__name__)

MAX_TESTO = 200      # caratteri di una frase: Needle lavora su frasi brevi
MAX_CORPO = 2048     # byte di una richiesta POST
CERT_GIORNI = 825    # massimo accettato da iOS per un certificato installato a mano
FONTS = Path(__file__).resolve().parents[1] / "fonts"
FONT_FILES = {"/fonts/SpaceGrotesk.ttf": "SpaceGrotesk.ttf",
              "/fonts/SpaceMono-Regular.ttf": "SpaceMono-Regular.ttf"}

Esegui = Callable[..., Any]


class Frase(NamedTuple):
    """Frase arrivata dal telefono, numerata dal server: `App.step` la passa a Needle."""
    id: int
    testo: str


def pulisci(testo: Any) -> str:
    """Testo della frase su una riga, senza caratteri di controllo, al massimo `MAX_TESTO`."""
    if not isinstance(testo, str):
        return ""
    return " ".join("".join(c if c.isprintable() else " " for c in testo).split())[:MAX_TESTO]


def _ip_locale() -> str:
    """Indirizzo del Pi sulla rete locale (nessun pacchetto parte: UDP non connette davvero)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return str(s.getsockname()[0])
    except OSError:
        return ""


def certificato(cartella: Path, esegui: Esegui = subprocess.run,
                host: str | None = None, ip: str | None = None) -> tuple[Path, Path]:
    """Certificato autofirmato (cert.pem, key.pem) in `cartella`, creato con openssl se manca.

    Vale per `<host>`, `<host>.local`, `localhost` e l'IP attuale del Pi. Solleva OSError o
    `subprocess.SubprocessError` se openssl non c'è o fallisce.
    """
    cert, key = cartella / "cert.pem", cartella / "key.pem"
    if cert.is_file() and key.is_file():
        return cert, key
    cartella.mkdir(parents=True, exist_ok=True)
    host = host if host is not None else socket.gethostname()
    ip = ip if ip is not None else _ip_locale()
    nomi = [f"DNS:{host}", f"DNS:{host}.local", "DNS:localhost", "IP:127.0.0.1"]
    if ip and ip != "127.0.0.1":
        nomi.append(f"IP:{ip}")
    esegui(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-nodes",
            "-days", str(CERT_GIORNI), "-keyout", str(key), "-out", str(cert),
            "-subj", f"/CN={host}.local", "-addext", "subjectAltName=" + ",".join(nomi),
            "-addext", "extendedKeyUsage=serverAuth"],
           check=True, capture_output=True, timeout=120)
    key.chmod(0o600)
    return cert, key


def contesto_tls(cfg: dict[str, Any], cartella: Path,
                 esegui: Esegui = subprocess.run) -> ssl.SSLContext | None:
    """Contesto TLS dal certificato configurato o da quello autofirmato; None = resta HTTP."""
    cert, key = str(cfg.get("cert") or ""), str(cfg.get("key") or "")
    try:
        if not cert:
            c, k = certificato(cartella, esegui)
            cert, key = str(c), str(k)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key or None)
    except (OSError, ssl.SSLError, subprocess.SubprocessError) as exc:
        log.warning("voce: niente HTTPS (%s): il microfono del browser non funzionerà, "
                    "la tastiera del telefono sì", exc)
        return None
    return ctx


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    tls: ssl.SSLContext | None = None

    def get_request(self) -> tuple[Any, Any]:
        sock, addr = super().get_request()
        if self.tls is not None:   # la stretta di mano avviene nel thread della richiesta
            sock = self.tls.wrap_socket(sock, server_side=True, do_handshake_on_connect=False)
        return sock, addr


class VoceServer:
    """Server della pagina "premi e parla": `/`, `/stato`, `POST /frase`."""

    def __init__(self, cfg: dict[str, Any], events: queue.Queue[Any],
                 stato: Callable[[], dict[str, Any]], tls: ssl.SSLContext | None = None) -> None:
        self.token = str(cfg.get("token") or "")
        self.events = events
        self.stato = stato
        self.https = tls is not None
        self._n = 0
        self._lock = threading.Lock()
        voce = self
        pagina = PAGINA.encode("utf-8")

        class Handler(BaseHTTPRequestHandler):
            timeout = 15    # un client lento o un certificato rifiutato non tengono il thread

            def handle(self) -> None:
                if isinstance(self.request, ssl.SSLSocket):
                    try:
                        self.request.do_handshake()
                    except (OSError, ssl.SSLError) as exc:   # es. certificato non ancora accettato
                        log.debug("voce: TLS: %s", exc)
                        return
                super().handle()

            def _send(self, code: int, body: bytes = b"", ctype: str = "application/json") -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def _json(self, code: int, data: dict[str, Any]) -> None:
                self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"))

            def _autorizzato(self) -> bool:
                if not voce.token:
                    return True
                dato = self.headers.get("X-Token") or (
                    parse_qs(urlsplit(self.path).query).get("t") or [""])[0]
                return hmac.compare_digest(dato.encode("utf-8"), voce.token.encode("utf-8"))

            def do_GET(self) -> None:  # noqa: N802
                path = urlsplit(self.path).path
                if path == "/":
                    self._send(200, pagina, "text/html; charset=utf-8")
                elif path in FONT_FILES:
                    try:
                        self._send(200, (FONTS / FONT_FILES[path]).read_bytes(), "font/ttf")
                    except OSError:
                        self._send(404)
                elif path == "/stato":
                    if not self._autorizzato():
                        self._json(403, {"errore": "codice mancante o sbagliato"})
                        return
                    self._json(200, {**voce.stato(), "https": voce.https})
                else:
                    self._send(404)

            def do_POST(self) -> None:  # noqa: N802
                if urlsplit(self.path).path != "/frase":
                    self._send(404)
                    return
                if not self._autorizzato():
                    self._json(403, {"errore": "codice mancante o sbagliato"})
                    return
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    n = -1
                if not 0 < n <= MAX_CORPO:
                    self._json(413 if n > MAX_CORPO else 400, {"errore": "richiesta non valida"})
                    return
                try:
                    dati = json.loads(self.rfile.read(n).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    dati = None
                testo = pulisci(dati.get("testo")) if isinstance(dati, dict) else ""
                if not testo:
                    self._json(400, {"errore": "frase vuota"})
                    return
                self._json(202, {"id": voce.invia(testo), "testo": testo})

            def log_message(self, fmt: str, *args: Any) -> None:
                log.debug("voce: " + fmt, *args)

        self._handler = Handler
        self._tls = tls
        self._server: _Server | None = None
        self.porta = 0

    def invia(self, testo: str) -> int:
        """Mette la frase nella coda del dashboard e ne restituisce il numero."""
        with self._lock:
            self._n += 1
            n = self._n
        self.events.put(Frase(n, testo))
        log.info("voce: frase dal telefono: %s", testo)
        return n

    def avvia(self, host: str, porta: int) -> int:
        """Apre la porta e serve in un thread; restituisce la porta vera (0 = scelta dal sistema)."""
        self._server = _Server((host, porta), self._handler)
        self._server.tls = self._tls
        threading.Thread(target=self._server.serve_forever, name="voce", daemon=True).start()
        vera = self.porta = int(self._server.server_address[1])
        log.info("voce: pagina \"premi e parla\" su %s://<pi>:%d/", "https" if self.https else "http",
                 vera)
        return vera

    def indirizzo(self, ip: str | None = None) -> str:
        """Indirizzo da aprire sul telefono (per il QR): IP del Pi, o `<nome>.local` se manca,
        con il codice d'accesso se c'è."""
        ip = _ip_locale() if ip is None else ip
        host = ip or f"{socket.gethostname()}.local"
        url = f"{'https' if self.https else 'http'}://{host}:{self.porta}/"
        return url + (f"?t={quote(self.token, safe='')}" if self.token else "")

    def close(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None


def avvia(cfg: dict[str, Any], events: queue.Queue[Any], stato: Callable[[], dict[str, Any]],
          cartella: Path, esegui: Esegui = subprocess.run) -> VoceServer | None:
    """Avvia il server se `voce.porta` è diversa da 0; None se spento o se la porta è occupata."""
    porta = int(cfg.get("porta") or 0)
    if not porta:
        return None
    server = VoceServer(cfg, events, stato, contesto_tls(cfg, cartella, esegui))
    try:
        server.avvia(str(cfg.get("host") or "0.0.0.0"), porta)
    except OSError as exc:
        log.error("voce: server non avviato sulla porta %d: %s", porta, exc)
        return None
    return server


PAGINA = """<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#1d1815">
<title>needle · voce</title>
<style>
@font-face{font-family:G;src:url(/fonts/SpaceGrotesk.ttf)}
@font-face{font-family:M;src:url(/fonts/SpaceMono-Regular.ttf)}
:root{--bg:#1d1815;--panel:#2a2320;--cream:#eee4cd;--tan:#a59b8c;--orange:#ee7b50;
      --amber:#f2bb5b;--pink:#e8505b;--line:#5b514a}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--cream)}
body{font-family:G,system-ui,sans-serif;min-height:100vh;display:flex;flex-direction:column;
     align-items:center;gap:16px;padding:16px;-webkit-user-select:none;user-select:none}
.w{width:100%;max-width:440px}
.lab{font-family:M,monospace;font-size:12px;color:var(--tan);letter-spacing:.04em}
header{display:flex;justify-content:space-between;align-items:center}
#dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--line);
     margin-right:7px;vertical-align:0}
.panel{background:var(--panel);border-radius:16px;padding:14px 16px;min-height:118px}
#detto{font-size:26px;line-height:1.2;min-height:1.2em;margin-top:6px;word-break:break-word}
#esito{font-size:18px;color:var(--amber);min-height:1.3em;margin-top:8px;word-break:break-word}
#parla{width:min(64vw,250px);aspect-ratio:1;border-radius:50%;border:0;margin:6px 0;
       background:var(--orange);color:var(--bg);font:600 24px/1.15 G,sans-serif;
       touch-action:none;-webkit-touch-callout:none;-webkit-tap-highlight-color:transparent;
       transition:transform .12s,background .12s}
#parla.on{background:var(--pink);transform:scale(1.06);animation:pulse 1.1s infinite}
#parla:disabled{background:var(--line);color:var(--tan)}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(232,80,91,.55)}100%{box-shadow:0 0 0 30px rgba(232,80,91,0)}}
#avviso{color:var(--amber);font-size:15px;margin:0;display:none}
form{display:flex;gap:8px}
input{flex:1;min-width:0;font:18px G,sans-serif;padding:12px 14px;border-radius:12px;
      border:1px solid var(--line);background:var(--panel);color:var(--cream);
      -webkit-user-select:text;user-select:text}
input::placeholder{color:var(--tan)}
button.s{font:600 16px G,sans-serif;padding:0 18px;border-radius:12px;border:0;
         background:var(--cream);color:var(--bg)}
#frasi{display:flex;flex-wrap:wrap;gap:8px;justify-content:center}
#frasi button{font:14px M,monospace;padding:8px 12px;border-radius:999px;
              border:1px solid var(--line);background:none;color:var(--cream)}
</style></head><body>
<header class="w"><span class="lab"><span id="dot"></span><span id="stato">needle</span></span>
<span class="lab">pi-dash · voce</span></header>
<div class="w panel"><div class="lab" id="lbl">tieni premuto e parla</div>
<div id="detto"></div><div id="esito"></div></div>
<button id="parla">premi<br>e parla</button>
<p class="w" id="avviso"></p>
<form class="w" id="f"><input id="t" maxlength="200" autocomplete="off" enterkeyhint="send"
 placeholder="scrivi o detta con la tastiera"><button class="s">invia</button></form>
<div class="w" id="frasi"></div>
<script>
"use strict";
const $=id=>document.getElementById(id);
const tok=new URLSearchParams(location.search).get('t')||'';
const H={'Content-Type':'application/json'};if(tok)H['X-Token']=tok;
const COLORI={pronto:'#f2bb5b','penso…':'#ee7b50',offline:'#e8505b'};
let attesa=false,frasi=false;
function avviso(t){const a=$('avviso');a.textContent=t;a.style.display=t?'block':'none';}
function esito(t){$('esito').textContent=t;}
async function stato(){
  try{
    const r=await fetch('/stato',{headers:H,cache:'no-store'});
    if(r.status===403){avviso('codice mancante o sbagliato: apri il link completo, con ?t=…');return null;}
    const s=await r.json();
    $('stato').textContent='needle · '+s.stato;
    $('dot').style.background=COLORI[s.stato]||'#5b514a';
    if(!frasi&&s.frasi){frasi=true;for(const q of s.frasi){const b=document.createElement('button');
      b.type='button';b.textContent=q;b.onclick=()=>invia(q);$('frasi').appendChild(b);}}
    return s;
  }catch(e){$('stato').textContent='pi-dash non risponde';$('dot').style.background='#e8505b';return null;}
}
const pausa=ms=>new Promise(r=>setTimeout(r,ms));
async function aspetta(id){
  const t0=Date.now();
  while(Date.now()-t0<40000){
    await pausa(400);
    const s=await stato();
    if(!s||s.id<id)continue;
    if(!s.accettata){esito('needle è occupato o spento: riprova');return;}
    if(s.risposte>s.attesa&&!s.lavora){
      esito(s.esito?'→ '+s.esito:(s.errore||(s.chiamate.length?s.chiamate.join(' · '):'non ho capito')));
      return;}
    esito('penso…');
  }
  esito('nessuna risposta');
}
async function invia(t){
  t=(t||'').trim().slice(0,200);
  if(!t||attesa)return;
  attesa=true;$('detto').textContent=t;esito('invio…');
  try{
    const r=await fetch('/frase',{method:'POST',headers:H,body:JSON.stringify({testo:t})});
    if(r.status===403){esito('');avviso('codice mancante o sbagliato: apri il link completo, con ?t=…');}
    else if(!r.ok)esito('frase non accettata');
    else await aspetta((await r.json()).id);
  }catch(e){esito('pi-dash non risponde');}
  attesa=false;
}
$('f').onsubmit=e=>{e.preventDefault();const t=$('t').value;$('t').value='';$('t').blur();invia(t);};
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
const btn=$('parla');
let rec=null,ascolto=false,detto='',t0=0;
if(!window.isSecureContext){btn.disabled=true;
  avviso('il microfono del browser funziona solo in https: apri l\\'indirizzo https:// del Pi. Intanto usa il microfono della tastiera qui sotto.');}
else if(!SR){btn.disabled=true;
  avviso('questo browser non riconosce la voce: usa Chrome o Safari, oppure il microfono della tastiera qui sotto.');}
function inizia(){
  if(ascolto||attesa)return;
  detto='';ascolto=true;t0=Date.now();
  rec=new SR();rec.lang='it-IT';rec.interimResults=true;rec.continuous=false;rec.maxAlternatives=1;
  rec.onresult=ev=>{let s='';for(const r of ev.results)s+=r[0].transcript;detto=s.trim();
    $('detto').textContent=detto;};
  rec.onerror=ev=>{
    if(ev.error==='not-allowed'||ev.error==='service-not-allowed')
      avviso('microfono non consentito: permettilo nelle impostazioni del sito e riprova.');
    else if(ev.error==='network')avviso('il riconoscimento vocale del telefono richiede internet.');
    else if(ev.error!=='no-speech'&&ev.error!=='aborted')avviso('riconoscimento: '+ev.error);};
  rec.onend=()=>{ascolto=false;btn.classList.remove('on');$('lbl').textContent='tieni premuto e parla';
    if(detto)invia(detto);else if(!$('esito').textContent)esito('non ho sentito nulla');};
  btn.classList.add('on');$('lbl').textContent='ascolto…';$('detto').textContent='';esito('');avviso('');
  if(navigator.vibrate)navigator.vibrate(25);
  try{rec.start();}catch(e){ascolto=false;btn.classList.remove('on');}
}
function smetti(){if(rec&&ascolto&&Date.now()-t0>350)rec.stop();}  // tocco breve: ascolta fino alla pausa
btn.addEventListener('pointerdown',e=>{e.preventDefault();
  if(ascolto&&Date.now()-t0>350){rec.stop();return;}
  btn.setPointerCapture(e.pointerId);inizia();});
btn.addEventListener('pointerup',smetti);
btn.addEventListener('pointercancel',smetti);
btn.addEventListener('contextmenu',e=>e.preventDefault());
stato();
setInterval(()=>{if(!document.hidden&&!attesa)stato();},4000);
</script></body></html>
"""
