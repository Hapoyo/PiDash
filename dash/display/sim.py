"""Simulatore: salva i fotogrammi in PNG e li serve su una pagina web
con i pulsanti virtuali (utile anche dal telefono sulla rete locale)."""
from __future__ import annotations

import io
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from PIL import Image

from ..inputs import frame_to_panel
from .base import Display

log = logging.getLogger(__name__)

_HTML = """<!doctype html><html lang="it"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>dashboard · simulatore</title>
<style>
body{background:%(bg)s;color:#cfcfc7;font-family:monospace;text-align:center;margin:1em}
img{width:100%%;max-width:%(maxw)dpx;image-rendering:pixelated;border:10px solid #3a3a36;
    border-radius:6px;cursor:crosshair}
button{font:inherit;font-size:1.1em;margin:.3em;padding:.6em 1em;background:#3a3a36;
       color:#e8e8e0;border:1px solid #666;border-radius:4px}
#s{opacity:.7;margin-top:.5em}
</style>
<img id="f" src="/frame.png" alt="frame">
<div><button data-k="next">N · pagina</button>
<button data-k="action">A · azione</button><button data-k="back">B · indietro</button></div>
<div id="s">refresh #<span id="n">-</span></div>
<script>
let last=-1;
async function poll(){
  try{const r=await fetch('/count');const n=+(await r.text());
      if(n!==last){last=n;document.getElementById('f').src='/frame.png?'+n;
                   document.getElementById('n').textContent=n;}}catch(e){}
}
setInterval(poll,120);
document.getElementById('f').onclick=e=>{const r=e.target.getBoundingClientRect(),b=10;
  const x=(e.clientX-r.left-b)/(r.width-2*b),y=(e.clientY-r.top-b)/(r.height-2*b);
  fetch('/tap?x='+x.toFixed(4)+'&y='+y.toFixed(4),{method:'POST'});};
document.querySelectorAll('button').forEach(b=>b.onclick=()=>fetch('/key/'+b.dataset.k,{method:'POST'}));
document.addEventListener('keydown',e=>{const m={n:'next',a:'action',b:'back'}[e.key];
  if(m)fetch('/key/'+m,{method:'POST'});});
</script></html>"""

VALID_KEYS = {"next", "action", "back"}


class SimDisplay(Display):
    """Display virtuale su file PNG (+ server HTTP opzionale)."""

    def __init__(self, width: int, height: int, cfg: dict[str, Any],
                 on_key: Callable[[str], None] | None = None, rotate: int = 0,
                 on_tap: Callable[[float, float], None] | None = None) -> None:
        super().__init__(width, height)
        self.rotate = rotate  # l'anteprima viene raddrizzata
        self.out_dir = Path(cfg.get("out_dir", "out"))
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.scale = max(1, int(cfg.get("scale", 2)))
        self.keep_frames = bool(cfg.get("keep_frames", False))
        self.count = 0
        self._png = b""
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        port = int(cfg.get("web_port", 0))
        if port:
            self._start_web(str(cfg.get("web_host", "127.0.0.1")), port, on_key, on_tap)

    def show(self, img: Image.Image) -> None:
        if self.rotate:
            img = img.rotate(self.rotate, expand=True)
        big = img.resize((img.width * self.scale, img.height * self.scale), Image.Resampling.NEAREST)
        buf = io.BytesIO()
        big.save(buf, format="PNG")
        data = buf.getvalue()
        with self._lock:
            self._png = data
            self.count += 1
            n = self.count
        target = self.out_dir / "frame.png"
        try:
            tmp = target.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(target)
            if self.keep_frames:
                (self.out_dir / f"frame_{n:05d}.png").write_bytes(data)
        except OSError as exc:
            log.error("impossibile scrivere %s: %s", target, exc)
        log.debug("[sim] fotogramma #%d", n)

    def _start_web(self, host: str, port: int, on_key: Callable[[str], None] | None,
                   on_tap: Callable[[float, float], None] | None = None) -> None:
        sim = self
        upright_w = self.height if self.rotate in (90, 270) else self.width
        page = (_HTML % {"maxw": upright_w * self.scale, "bg": "#1d1815"}).encode("utf-8")

        class Handler(BaseHTTPRequestHandler):
            def _send(self, code: int, body: bytes = b"", ctype: str = "text/plain") -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                path = self.path.split("?", 1)[0]
                if path == "/":
                    self._send(200, page, "text/html; charset=utf-8")
                elif path == "/frame.png":
                    with sim._lock:
                        data = sim._png
                    self._send(200 if data else 503, data, "image/png")
                elif path == "/count":
                    self._send(200, str(sim.count).encode())
                else:
                    self._send(404)

            def do_POST(self) -> None:  # noqa: N802
                key = self.path.rsplit("/", 1)[-1]
                url = urlparse(self.path)
                if url.path == "/tap" and on_tap:  # clic sull'anteprima = tocco sul pannello
                    q = parse_qs(url.query)
                    try:
                        x, y = float(q["x"][0]), float(q["y"][0])
                    except (KeyError, ValueError):
                        self._send(400)
                        return
                    on_tap(*frame_to_panel(min(1.0, max(0.0, x)), min(1.0, max(0.0, y)), sim.rotate))
                    self._send(204)
                elif self.path.startswith("/key/") and key in VALID_KEYS and on_key:
                    on_key(key)
                    self._send(204)
                else:
                    self._send(404)

            def log_message(self, fmt: str, *args: Any) -> None:
                log.debug("web: " + fmt, *args)

        try:
            self._server = ThreadingHTTPServer((host, port), Handler)
        except OSError as exc:
            log.error("server web non avviato su %s:%d: %s", host, port, exc)
            return
        threading.Thread(target=self._server.serve_forever, name="web", daemon=True).start()
        log.info("simulatore web: http://%s:%d/", host, port)

    def close(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
