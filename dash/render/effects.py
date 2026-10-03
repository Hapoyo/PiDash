"""Disegno delle animazioni sopra la pagina base e dei riquadri che la coprono.

I tempi stanno in `dash/motion.py`; qui solo il disegno di ogni effetto per un istante `t`.
"""
from __future__ import annotations

import zlib
from typing import TYPE_CHECKING

from PIL import Image

from ..layout import Box
from ..motion import Fx, Slot, ease_in_out, scramble, wave
from . import bot
from .canvas import Canvas
from .theme import fit

if TYPE_CHECKING:
    from ..app import App

SIGLA = "Pi-Dash"  # nome scritto dalla sequenza di avvio


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
                     width=cv.line)
    elif e.kind == "bot":        # faccia del bot di Needle: si ridisegna tutta, sul fondo pulito
        cv.d.rectangle(e.box, fill=cv.c[e.bg])
        bot.draw(cv, e.box, bot.MOODS[int(e.extra[0])], t, e.bg)
    elif e.kind == "outline":    # voce scelta della scheda "+"
        r, lw = (e.extra + (8, 2))[:2]
        cv.d.rounded_rectangle(e.box, radius=round(r), outline=cv.mix(e.color, e.bg, wave(t, 1.4)),
                               width=round(lw))


def clear(cv: Canvas, box: tuple[int, int, int, int], bg: str, base: Image.Image | None) -> None:
    """Cancella `box` con il fondo: riga per riga dalla pagina base (i pannelli a rilievo hanno
    una sfumatura verticale), altrimenti con il colore piatto `bg`."""
    x0, y0, x1, y1 = box
    if base is None or not (0 <= x0 - 1 and x1 < base.width):
        cv.d.rectangle(box, fill=cv.c[bg])
        return
    for y in range(max(0, y0), min(base.height, y1 + 1)):
        cv.d.line((x0, y, x1, y), fill=base.getpixel((x0 - 1, y)))


def draw_decode(cv: Canvas, slot: Slot, p: float, keep: str, frame_no: int,
                base: Image.Image | None = None) -> None:
    """Cifre che scorrono e si fermano da sinistra a destra, ognuna al suo posto finale."""
    seed = zlib.crc32(slot.key.encode()) ^ frame_no  # riproducibile fra esecuzioni
    text = scramble(slot.text, p, seed, keep)
    if text == slot.text:
        return
    clear(cv, slot.box, slot.bg, base)
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
    lw = cv.px(2)
    cv.d.rectangle((0, y, w, y + lw), fill=cv.c["orange"])
    cv.d.line((0, y + lw + 1, w, y + lw + 1), fill=cv.mix("amber", "bg", 0.5))
    return out


def boot(w: int, h: int, u: float, colors: dict[str, tuple[int, int, int]], app: App,
         p: float) -> Image.Image:
    """Sequenza di accensione: sigla che si scrive, righe di controllo, barra di carico."""
    from .. import __version__
    cv = Canvas(Image.new("RGB", (w, h), colors["bg"]), colors, u)
    m = cv.px(12)
    loc = getattr(getattr(app.pages[0].widget, "location", None), "name", "") or "--"
    righe = [f"schermo {w}×{h}", f"schede {len(app.pages)}", f"posizione {loc.lower()}",
             "meteo open-meteo", "sistema pronto"]
    cv.label((m, m), f"{SIGLA} // v{__version__}", "tan", small=True, lower=False)
    cv.label((w - m, m), "avvio", "tan", "ra", small=True)
    # sigla: si scrive una lettera alla volta, con il cursore a blocco
    sigla = SIGLA
    n = min(len(sigla), int(len(sigla) * min(1.0, p / 0.35)) + 1)
    f = fit(sigla, "grotesk", 600, w - 2 * m, h * 0.24)
    base_y = round(h * 0.36)
    cv.text((m, base_y), sigla[:n], f, "cream", "ls")
    cur_x = m + f.getlength(sigla[:n]) + cv.px(4)
    if p < 0.9 and (p * 10) % 1 < 0.6:
        cv.d.rectangle((cur_x, base_y - round(f.size * 0.7), cur_x + round(f.size * 0.35), base_y),
                       fill=cv.c["orange"])
    # righe di controllo: compaiono una dopo l'altra, puntini fino a "ok" in arancio
    step = cv.height(cv.f_label) + cv.px(5)
    y = base_y + cv.px(12)
    dot = cv.f_label.getlength(".")
    for i, r in enumerate(righe):
        if p < 0.25 + i * 0.12:
            break
        cv.label((m, y), r, "cream", lower=False)
        dots_x = m + cv.f_label.getlength(r) + cv.px(4)
        end = w - m - cv.f_label.getlength("ok") - cv.px(4)
        if end > dots_x:
            cv.label((dots_x, y), "." * int((end - dots_x) / max(1, dot)), "line")
        cv.label((w - m, y), "ok", "orange", "ra")
        y += step
    # barra di carico in basso, come le barre delle altre pagine
    bar = Box(m, h - m - cv.px(6), w - 2 * m, cv.px(6))
    k = ease_in_out(p)
    cv.progress(bar, k, "orange")
    cv.label((bar.x, bar.y - cv.px(4)), f"carico {k * 100:.0f}%", "tan", "ld", small=True)
    return cv.img


def alert(cv: Canvas, w: int, h: int, msg: str, touch: bool) -> None:
    """Riquadro rosa di sveglia o timer scaduto, sopra qualsiasi pagina."""
    notice(cv, w, h, msg, "tocca lo schermo" if touch else "premi a")


def notice(cv: Canvas, w: int, h: int, msg: str, hint: str) -> None:
    """Riquadro rosa al centro dello schermo: allarmi e spegnimento."""
    b = Box(round(w * 0.15), round(h * 0.32), round(w * 0.7), round(h * 0.36))
    cv.rect(b, "pink", "cream", cv.px(3), r=cv.px(14))
    hint_h = cv.height(cv.f_label) + 2 * cv.gap
    num = Box(b.x + 2 * cv.pad, b.y + 2 * cv.pad, b.w - 4 * cv.pad, b.h - 3 * cv.pad - hint_h)
    cv.big(num, msg.lower(), "paper", 600, pos=(b.x + b.w / 2, num.bottom), anchor="ms")
    cv.label((b.x + b.w / 2, b.bottom - cv.pad), hint, "paper", "md")
