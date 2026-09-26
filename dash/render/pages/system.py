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
    u = cv.u
    sysw: Any = app.page.widget
    st, hist = sysw.snapshot()
    r, pad, g = round(20 * u), max(4, round(11 * u)), round(10 * u)
    top = Box(b.x, b.y, b.w, round(b.h * 0.46))
    cells = [("cpu", st.cpu, "orange"), ("ram", st.ram_frac, "cream"), ("disco", st.disk_frac, "tan")]
    cw = (top.w - 2 * g) / 3
    for i, (k, v, col) in enumerate(cells):
        cb = Box(round(top.x + i * (cw + g)), top.y, round(cw), top.h)
        cv.panel(cb, col, k, f"{v * 100:.0f}%" if v is not None else "--", "", r,
                 ref="100%", slot=f"system.{k}", live=True)
    # storici affiancati: cpu in percentuale, rete in scala sul massimo mostrato
    net = sysw.net_snapshot()
    gh = round(b.h * 0.26)
    gw = (b.w - g) / 2
    cpu_box = Box(b.x, top.bottom + g, round(gw), gh)
    net_box = Box(round(b.x + gw + g), top.bottom + g, round(gw), gh)
    picco = max(net) if net else 0.0
    cv.graph(cpu_box, hist, 1.0, "cpu · storico", "amber", r, pad)
    cv.graph(net_box, net, picco, f"rete · picco {rate_str(picco)}", "orange", r, pad)
    rows = Box(b.x, cpu_box.bottom + g, b.w, b.bottom - cpu_box.bottom - g)
    info = [("host", st.host), ("ip", st.ip or "--"),
            ("rete", f"giù {rate_str(st.net_rx)} · su {rate_str(st.net_tx)}"),
            ("temp", f"{st.temp_c:.0f}°C" if st.temp_c else "--"),
            ("uptime", uptime_str(st.uptime_s))]
    cv.rows(rows, info, lower=False)
