"""Disegno del dashboard.

- `theme.py`    colori, font, cache dei testi
- `canvas.py`   primitive dello stile (testi, pannelli, anelli, barre, righe, grafici)
- `folders.py`  schedario: geometria delle linguette e disegno delle cartelle
- `pages/`      una funzione `draw` per tipo di pagina
- `effects.py`  animazioni sopra la pagina base e riquadro di allarme
- `renderer.py` `CyberRenderer`: pagina base e fotogrammi animati
"""
from .renderer import CyberRenderer
from .theme import PALETTE, font, text_mask

__all__ = ["CyberRenderer", "PALETTE", "font", "text_mask"]
