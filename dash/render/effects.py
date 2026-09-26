"""Disegno delle animazioni sopra la pagina base e dei riquadri che la coprono.

I tempi stanno in `dash/motion.py`; qui solo il disegno di ogni effetto per un istante `t`.
"""
from __future__ import annotations

import zlib
from typing import TYPE_CHECKING

from PIL import Image

from ..layout import Box
from ..motion import Fx, Slot, ease_in_out, scramble, wave
from .canvas import Canvas
from .theme import fit, font

if TYPE_CHECKING:
    from ..app import App


def draw_fx(cv: Canvas, e: Fx, t: float) -> None:
    """Effetto continuo registrato durante il disegno della pagina."""
    x0, y0, x1, y1 = e.box
    if e.kind == "blink":        # due punti: mezzo secondo sì, mezzo no
        if t % 1.0 >= 0.5:
            cv.d.rectangle(e.box, fill=cv.c[e.bg])
    elif e.kind == "led":        # spia della linguetta aperta
        on = wave(t, 1.6) > 0.35
        cv.d.rectangle(e.box, fill=cv.c[e.color] if on else cv.mix(e.color, e.bg, 0.8))
    elif e.kind == "pulse":      # alone che si allarga e sfuma attorno alla sfera
        k = ((t / 2.2) + e.phase) % 1.0
        cx, cy, r = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2
        rr = r * (1.4 + 2.2 * k)
        cv.d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=cv.mix(e.color, e.bg, k),
                     width=max(1, round(1.5 * cv.u)))
    elif e.kind == "outline":    # voce scelta della scheda "+"
        r, lw = (e.extra + (8, 2))[:2]
        cv.d.rounded_rectangle(e.box, radius=round(r), outline=cv.mix(e.color, e.bg, wave(t, 1.4)),
                               width=round(lw))


def draw_decode(cv: Canvas, slot: Slot, p: float, keep: str, frame_no: int) -> None:
    """Cifre che scorrono e si fermano da sinistra a destra, ognuna al suo posto finale."""
    seed = zlib.crc32(slot.key.encode()) ^ frame_no  # riproducibile fra esecuzioni
    text = scramble(slot.text, p, seed, keep)
    if text == slot.text:
        return
    cv.d.rectangle(slot.box, fill=cv.c[slot.bg])
    x = cv.left(slot.text, slot.font, slot.xy[0], slot.anchor)
    for i, c in enumerate(text):
        cx = x + slot.font.getlength(slot.text[:i])
        if c == slot.text[i]:
            cv.text((cx, slot.xy[1]), c, slot.font, slot.fill, "ls")
        else:  # cifra di passaggio centrata nella cella di quella finale, come un rullo
            mid = cx + slot.font.getlength(slot.text[i]) / 2
            cv.text((mid, slot.xy[1]), c, slot.font, cv.mix(slot.fill, slot.bg, 0.35), "ms")


def wipe(old: Image.Image, new: Image.Image, p: float, colors: dict[str, tuple[int, int, int]],
         u: float) -> Image.Image:
    """Scansione dall'alto: sopra la riga la pagina nuova, sotto quella vecchia."""
    w, h = new.size
    y = round(h * p)
    out = old.copy() if old.size == new.size else Image.new("RGB", new.size, colors["bg"])
    if y > 0:
        out.paste(new.crop((0, 0, w, y)), (0, 0))
    cv = Canvas(out, colors, u)
    lw = max(1, round(3 * u))
    cv.d.rectangle((0, y, w, y + lw), fill=cv.c["orange"])
    cv.d.line((0, y + lw + 1, w, y + lw + 1), fill=cv.mix("amber", "bg", 0.5))
    return out


def boot(w: int, h: int, u: float, colors: dict[str, tuple[int, int, int]], app: App,
         p: float) -> Image.Image:
    """Sequenza di accensione: sigla che si scrive, righe di controllo, barra di carico."""
    from .. import __version__
    cv = Canvas(Image.new("RGB", (w, h), colors["bg"]), colors, u)
    m = round(24 * u)
    loc = getattr(getattr(app.pages[0].widget, "location", None), "name", "") or "--"
    righe = [f"schermo {w}×{h}", f"schede {len(app.pages)}", f"posizione {loc.lower()}",
             "meteo open-meteo", "sistema pronto"]
    cv.micro((m, m), f"pi-dash // v{__version__}", "tan", "la", 12)
    cv.micro((w - m, m), "avvio", "tan", "ra", 12)
    # sigla: si scrive una lettera alla volta, con il cursore a blocco
    sigla = "pi-dash"
    n = min(len(sigla), int(len(sigla) * min(1.0, p / 0.35)) + 1)
    f = fit(sigla, "grotesk", 600, w - 2 * m, h * 0.26)
    base_y = round(h * 0.42)
    cv.text((m, base_y), sigla[:n], f, "cream", "ls")
    cur_x = m + f.getlength(sigla[:n]) + round(6 * u)
    if p < 0.9 and (p * 10) % 1 < 0.6:
        cv.d.rectangle((cur_x, base_y - round(f.size * 0.7), cur_x + round(f.size * 0.35), base_y),
                       fill=cv.c["orange"])
    # righe di controllo: compaiono una dopo l'altra, "ok" in arancio
    line_h = round(19 * u)
    y = base_y + round(18 * u)
    mono = font("mono", round(12 * u))
    for i, r in enumerate(righe):
        if p < 0.25 + i * 0.12:
            break
        cv.text((m, y), r, mono, "cream", "la")
        dots_x = m + mono.getlength(r) + round(6 * u)
        end = w - m - mono.getlength("ok") - round(6 * u)
        if end > dots_x:
            cv.text((dots_x, y), "." * int((end - dots_x) / max(1, mono.getlength("."))), mono,
                    "line", "la")
        cv.text((w - m, y), "ok", mono, "orange", "ra")
        y += line_h
    # barra di carico in basso, stile delle altre pagine
    bar = Box(m, h - m - round(8 * u), w - 2 * m, max(3, round(8 * u)))
    k = ease_in_out(p)
    cv.progress(bar, k, "orange")
    cv.micro((bar.x, bar.y - round(6 * u)), f"carico {k * 100:.0f}%", "tan", "ld", 11)
    return cv.img


def alert(cv: Canvas, w: int, h: int, msg: str, touch: bool) -> None:
    """Riquadro rosa di sveglia o timer scaduto, sopra qualsiasi pagina."""
    u = cv.u
    b = Box(round(w * 0.2), round(h * 0.38), round(w * 0.6), round(h * 0.24))
    cv.rect(b, round(24 * u), "pink", "cream", max(2, round(4 * u)))
    cv.big(b.inset(round(20 * u), round(24 * u)), msg.lower(), "paper", 600,
           pos=(b.x + b.w / 2, b.y + b.h * 0.62), anchor="ms")
    cv.micro((b.x + b.w / 2, b.bottom - round(18 * u)), "tocca lo schermo" if touch else "premi a",
             "paper", "mm")
