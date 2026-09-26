"""Display su framebuffer Linux (/dev/fbN): schermi SPI tipo 3,5" ILI9486, HDMI.

Scrive direttamente nel framebuffer, senza desktop grafico: adatto a Raspberry Pi OS Lite.
Formati supportati: 16 bpp (RGB565) e 32 bpp (XRGB8888).

Scrive solo le fasce di righe cambiate rispetto al fotogramma precedente: sul bus SPI a 18 MHz
uno schermo intero costa ~0,14 s, una fascia di 16 righe meno di 10 ms. Le animazioni toccano
zone piccole, quindi restano fluide.
"""
from __future__ import annotations

import fcntl
import logging
import os
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops

from .base import Display

log = logging.getLogger(__name__)

KDSETMODE = 0x4B3A
KD_TEXT, KD_GRAPHICS = 0x00, 0x01
SYS_FB = Path("/sys/class/graphics")
DEV_DIR = Path("/dev")
PANEL_NAMES = ("ili9486", "ili9341", "st7796", "hx8357", "fb_")  # driver SPI noti


def _sys(fb: str, attr: str) -> str:
    return (SYS_FB / fb / attr).read_text(encoding="ascii").strip()


def fb_info(fb: str) -> tuple[int, int, int, int, str]:
    """(larghezza, altezza, bpp, stride, nome) dal sysfs; stride = byte per riga."""
    w, h = (int(v) for v in _sys(fb, "virtual_size").split(","))
    bpp = int(_sys(fb, "bits_per_pixel"))
    try:
        stride = int(_sys(fb, "stride"))
    except (OSError, ValueError):
        stride = w * bpp // 8
    try:
        name = _sys(fb, "name")
    except OSError:
        name = ""
    return w, h, bpp, stride, name


def find_panel() -> str:
    """Primo framebuffer di un pannello SPI (per nome del driver), altrimenti fb0."""
    fbs = sorted(p.name for p in SYS_FB.glob("fb[0-9]*"))
    for fb in fbs:
        try:
            name = fb_info(fb)[4].lower()
        except (OSError, ValueError):
            continue
        if any(k in name for k in PANEL_NAMES):
            return fb
    if not fbs:
        raise RuntimeError("nessun framebuffer trovato: controlla dtoverlay in config.txt")
    return fbs[0]


STRIPE = 16  # righe per fascia nel confronto fra fotogrammi


def dirty_bands(old: Image.Image, new: Image.Image, stripe: int = STRIPE) -> list[tuple[int, int]]:
    """Fasce di righe [y0, y1) diverse fra due fotogrammi della stessa misura."""
    diff = ImageChops.difference(old, new)
    w, h = new.size
    bands: list[tuple[int, int]] = []
    for y in range(0, h, stripe):
        y1 = min(h, y + stripe)
        box = diff.crop((0, y, w, y1)).getbbox()
        if box is None:
            continue
        top, bottom = y + box[1], y + box[3]
        if bands and bands[-1][1] >= y:   # fascia contigua alla precedente: si uniscono
            bands[-1] = (bands[-1][0], bottom)
        else:
            bands.append((top, bottom))
    return bands


def pack(img: Image.Image, bpp: int) -> bytes:
    """Converte un fotogramma RGB nel formato del framebuffer."""
    r, g, b = img.convert("RGB").split()
    if bpp == 16:  # RGB565 little-endian: byte basso GGGBBBBB, byte alto RRRRRGGG
        hi = ImageChops.add(r.point(lambda v: v & 0xF8), g.point(lambda v: v >> 5))
        lo = ImageChops.add(g.point(lambda v: (v << 3) & 0xE0), b.point(lambda v: v >> 3))
        return Image.merge("LA", (lo, hi)).tobytes()
    if bpp == 32:  # in memoria: B, G, R, X
        return Image.merge("RGBA", (b, g, r, Image.new("L", img.size, 255))).tobytes()
    raise RuntimeError(f"formato framebuffer non supportato: {bpp} bpp")


class FramebufferDisplay(Display):
    """Pannello su /dev/fbN; risoluzione "auto" = quella del framebuffer ÷ pixel_scale."""

    def __init__(self, width: int | str, height: int | str, cfg: dict[str, Any]) -> None:
        super().__init__(0, 0)
        device = str(cfg.get("device", "auto"))
        fb = find_panel() if device == "auto" else Path(device).name
        self.fb_w, self.fb_h, self.bpp, self.stride, name = fb_info(fb)
        scale = max(1, int(cfg.get("pixel_scale", 1)))
        self.width = self.fb_w // scale if width == "auto" else int(width)
        self.height = self.fb_h // scale if height == "auto" else int(height)
        path = str(DEV_DIR / fb)
        try:
            self._fh = open(path, "r+b", buffering=0)
        except PermissionError as exc:
            raise RuntimeError(f"{path}: permesso negato (l'utente deve essere nel gruppo 'video')") from exc
        self._tty: int | None = None
        self._prev: Image.Image | None = None  # ultimo fotogramma scritto, per le fasce cambiate
        if cfg.get("console_off", True):
            self._console(KD_GRAPHICS)
        log.info("framebuffer %s (%s) %d×%d %d bpp, disegno %d×%d",
                 path, name, self.fb_w, self.fb_h, self.bpp, self.width, self.height)

    def _console(self, mode: int) -> None:
        """Ferma (o riattiva) la console di testo, che altrimenti scrive sopra il dashboard."""
        try:
            if self._tty is None:
                try:
                    self._tty = os.open("/dev/tty0", os.O_RDWR)
                except PermissionError:  # gruppo tty: solo scrittura
                    self._tty = os.open("/dev/tty0", os.O_WRONLY)
            fcntl.ioctl(self._tty, KDSETMODE, mode)
        except OSError as exc:
            log.debug("console non gestita (%s): vedi docs/hardware.md", exc)
            if self._tty is not None:
                os.close(self._tty)
                self._tty = None

    def show(self, img: Image.Image) -> None:
        if img.size != (self.fb_w, self.fb_h):
            img = img.resize((self.fb_w, self.fb_h), Image.Resampling.NEAREST)
        img = img.convert("RGB")
        prev, self._prev = self._prev, img
        bands = [(0, self.fb_h)] if prev is None else dirty_bands(prev, img)
        row = self.fb_w * self.bpp // 8
        try:
            for y0, y1 in bands:
                data = pack(img.crop((0, y0, self.fb_w, y1)), self.bpp)
                if self.stride == row:  # righe contigue in memoria: una sola scrittura
                    self._fh.seek(y0 * self.stride)
                    self._fh.write(data)
                else:
                    for y in range(y0, y1):
                        self._fh.seek(y * self.stride)
                        self._fh.write(data[(y - y0) * row:(y - y0 + 1) * row])
        except OSError as exc:
            self._prev = None  # al prossimo giro si riscrive tutto
            log.error("scrittura framebuffer fallita: %s", exc)

    def close(self) -> None:
        if self._tty is not None:
            self._console(KD_TEXT)          # può chiudere il descrittore in caso di errore
            tty, self._tty = self._tty, None
            try:
                os.close(tty)
            except OSError:
                pass
        self._fh.close()
