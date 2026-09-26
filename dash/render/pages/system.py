"""Sistema: CPU, RAM e disco in pannelli a colori, storici di CPU e rete, dati della macchina."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from ...layout import Box
from ...widgets.system import rate_str, uptime_str
from ..canvas import Canvas

if TYPE_CHECKING:
    from ...app import App


def draw(cv: Canvas, b: Box, app: App, now: datetime) -> None:
    sysw: Any = app.page.widget
    st, hist = sysw.snapshot()
    net = sysw.net_snapshot()
    g = cv.gap
    # riga 1: tre pannelli con la stessa taglia di numero
    top = Box(b.x, b.y, b.w, round(b.h * 0.40))
    cells = [("cpu", st.cpu, "orange"), ("ram", st.ram_frac, "cream"), ("disco", st.disk_frac, "tan")]
    cw = (top.w - 2 * g) / 3
    for i, (k, v, col) in enumerate(cells):
        cb = Box(round(top.x + i * (cw + g)), top.y, round(cw), top.h)
        cv.panel(cb, col, k, f"{v * 100:.0f}%" if v is not None else "--", ref="100%",
                 slot=f"system.{k}", live=True)
    # riga 2: storici affiancati, rete in scala sul picco mostrato
    rows_h = cv.row_step() + cv.height(cv.f_label)
    graphs = Box(b.x, top.bottom + g, b.w, b.bottom - rows_h - g - (top.bottom + g))
    gw = (b.w - g) / 2
    cpu_box = Box(b.x, graphs.y, round(gw), graphs.h)
    net_box = Box(round(b.x + gw + g), graphs.y, round(b.right - b.x - gw - g), graphs.h)
    cv.graph(cpu_box, hist, 1.0, "cpu", "amber")
    cv.graph(net_box, net, max(net) if net else 0.0,
             f"rete ↓{rate_str(st.net_rx)} ↑{rate_str(st.net_tx)}", "orange")
    # riga 3: dati della macchina su due colonne, allineate ai grafici
    rows = Box(b.x, b.bottom - rows_h, b.w, rows_h)
    key_w = round(cv.f_label.getlength("uptime ")) + cv.px(4)  # colonna dei valori
    cv.rows(Box(rows.x + cv.pad, rows.y, cpu_box.w - cv.pad, rows.h),
            [("host", st.host), ("ip", st.ip or "--")], lower=False, value_x=key_w)
    cv.rows(Box(net_box.x + cv.pad, rows.y, net_box.w - cv.pad, rows.h),
            [("temp", f"{st.temp_c:.0f} °C" if st.temp_c else "--"),
             ("uptime", uptime_str(st.uptime_s))], lower=False, value_x=key_w)
