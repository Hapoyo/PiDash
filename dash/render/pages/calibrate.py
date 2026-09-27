"""Calibrazione del touch: schermo intero con una croce alla volta."""
from __future__ import annotations

from typing import Any

from ..canvas import Canvas
from ..theme import fit

CROSS = 14   # mezza lunghezza dei bracci della croce (pixel a 480×320)


def draw_screen(cv: Canvas, w: int, h: int, wizard: Any) -> None:
    """Croce da toccare, avanzamento e spiegazione al centro."""
    from ...widgets.calibrate import TARGETS
    target = wizard.target()
    titolo = "calibra touch"
    cv.text((w / 2, h * 0.42), titolo, fit(titolo, "grotesk", 600, w * 0.6, h * 0.1), "cream", "ms")
    cv.label((w / 2, h * 0.42 + cv.gap), "tocca il centro della croce arancio", "tan", "ma")
    cv.label((w / 2, h * 0.42 + cv.gap + cv.row_step()),
             f"punto {min(wizard.step + 1, len(TARGETS))} di {len(TARGETS)} · "
             "senza tocchi si annulla in 30 s", "tan", "ma", small=True)
    for i, (fx, fy) in enumerate(TARGETS):  # croci già toccate in grigio, prossime appena accennate
        x, y = fx * w, fy * h
        if (fx, fy) == target:
            continue
        col = "line" if i < wizard.step else "panel"
        arm = cv.px(CROSS / 2)
        cv.d.line((x - arm, y, x + arm, y), fill=cv.c[col], width=cv.line)
        cv.d.line((x, y - arm, x, y + arm), fill=cv.c[col], width=cv.line)
    if target is not None:
        x, y = target[0] * w, target[1] * h
        arm, ring = cv.px(CROSS), cv.px(6)
        cv.d.line((x - arm, y, x + arm, y), fill=cv.c["orange"], width=cv.stroke)
        cv.d.line((x, y - arm, x, y + arm), fill=cv.c["orange"], width=cv.stroke)
        cv.d.ellipse((x - ring, y - ring, x + ring, y + ring), outline=cv.c["amber"], width=cv.line)
        cv.add_fx("pulse", (x - ring, y - ring, x + ring, y + ring), "orange", "bg")
