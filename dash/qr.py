"""QR code senza dipendenze: testo → matrice di moduli (True = scuro). Nessun disegno.

Serve un QR piccolo (l'indirizzo della pagina "premi e parla"), quindi solo modo byte (UTF-8),
versioni 1–10 e correzione L o M. La maschera è quella con la penalità più bassa, come chiede
lo standard (ISO/IEC 18004). Struttura ripresa da qrcodegen di Project Nayuki (MIT).
"""
from __future__ import annotations

MAX_VERSIONE = 10
# per livello: codewords di correzione per blocco e numero di blocchi, indice = versione
_ECC = {"L": [-1, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18],
        "M": [-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26]}
_BLOCCHI = {"L": [-1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4],
            "M": [-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5]}
_FORMATO = {"L": 1, "M": 0}   # bit del livello nelle informazioni di formato


def _moduli_dati(v: int) -> int:
    """Moduli disponibili per dati e correzione nella versione `v`."""
    n = (16 * v + 128) * v + 64
    if v >= 2:
        a = v // 7 + 2
        n -= (25 * a - 10) * a - 55
        if v >= 7:
            n -= 36
    return n


def _codewords_dati(v: int, livello: str) -> int:
    return _moduli_dati(v) // 8 - _ECC[livello][v] * _BLOCCHI[livello][v]


def _gf_mul(x: int, y: int) -> int:
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisore(grado: int) -> list[int]:
    res = [0] * (grado - 1) + [1]
    root = 1
    for _ in range(grado):
        for j in range(grado):
            res[j] = _gf_mul(res[j], root)
            if j + 1 < grado:
                res[j] ^= res[j + 1]
        root = _gf_mul(root, 0x02)
    return res


def _rs_resto(dati: list[int], divisore: list[int]) -> list[int]:
    res = [0] * len(divisore)
    for b in dati:
        f = b ^ res.pop(0)
        res.append(0)
        for i, coef in enumerate(divisore):
            res[i] ^= _gf_mul(coef, f)
    return res


def _allineamento(v: int) -> list[int]:
    if v == 1:
        return []
    n = v // 7 + 2
    passo = (v * 8 + n * 3 + 5) // (n * 4 - 4) * 2
    return [6] + [v * 4 + 17 - 7 - i * passo for i in range(n - 1)][::-1]


def _bch(dati: int, bits: int, gen: int, gen_bits: int) -> int:
    rem = dati
    for _ in range(bits):
        rem = (rem << 1) ^ ((rem >> (gen_bits - 2)) * gen)
    return rem


class _Matrice:
    def __init__(self, v: int) -> None:
        self.v = v
        self.n = v * 4 + 17
        self.m = [[False] * self.n for _ in range(self.n)]
        self.fisso = [[False] * self.n for _ in range(self.n)]

    def metti(self, x: int, y: int, scuro: bool) -> None:
        self.m[y][x] = scuro
        self.fisso[y][x] = True

    def funzioni(self) -> None:
        n = self.n
        for i in range(n):                          # linee di temporizzazione
            self.metti(6, i, i % 2 == 0)
            self.metti(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):   # tre quadrati di posizione
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < n and 0 <= y < n:
                        d = max(abs(dx), abs(dy))
                        self.metti(x, y, d not in (2, 4))
        pos = _allineamento(self.v)
        for i, a in enumerate(pos):
            for j, b in enumerate(pos):
                if (i == 0 and j == 0) or (i == 0 and j == len(pos) - 1) or \
                        (i == len(pos) - 1 and j == 0):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.metti(a + dx, b + dy, max(abs(dx), abs(dy)) != 1)
        self.formato("L", 0)                        # riserva le zone, valori veri dopo
        if self.v >= 7:
            bits = self.v << 12 | _bch(self.v, 12, 0x1F25, 13)
            for i in range(18):
                bit = (bits >> i) & 1 == 1
                a, b = n - 11 + i % 3, i // 3
                self.metti(a, b, bit)
                self.metti(b, a, bit)

    def formato(self, livello: str, maschera: int) -> None:
        dati = _FORMATO[livello] << 3 | maschera
        bits = (dati << 10 | _bch(dati, 10, 0x537, 11)) ^ 0x5412
        n = self.n
        for i in range(6):
            self.metti(8, i, (bits >> i) & 1 == 1)
        self.metti(8, 7, (bits >> 6) & 1 == 1)
        self.metti(8, 8, (bits >> 7) & 1 == 1)
        self.metti(7, 8, (bits >> 8) & 1 == 1)
        for i in range(9, 15):
            self.metti(14 - i, 8, (bits >> i) & 1 == 1)
        for i in range(8):
            self.metti(n - 1 - i, 8, (bits >> i) & 1 == 1)
        for i in range(8, 15):
            self.metti(8, n - 15 + i, (bits >> i) & 1 == 1)
        self.metti(8, n - 8, True)                  # modulo sempre scuro

    def codewords(self, dati: list[int]) -> None:
        n, i = self.n, 0
        destra = n - 1
        while destra >= 1:
            if destra == 6:
                destra = 5
            for vert in range(n):
                for j in range(2):
                    x = destra - j
                    su = ((destra + 1) & 2) == 0
                    y = n - 1 - vert if su else vert
                    if not self.fisso[y][x] and i < len(dati) * 8:
                        self.m[y][x] = (dati[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1
            destra -= 2

    def maschera(self, k: int) -> None:
        for y in range(self.n):
            for x in range(self.n):
                if self.fisso[y][x]:
                    continue
                inv = (k == 0 and (x + y) % 2 == 0) or (k == 1 and y % 2 == 0) or \
                      (k == 2 and x % 3 == 0) or (k == 3 and (x + y) % 3 == 0) or \
                      (k == 4 and (x // 3 + y // 2) % 2 == 0) or \
                      (k == 5 and x * y % 2 + x * y % 3 == 0) or \
                      (k == 6 and (x * y % 2 + x * y % 3) % 2 == 0) or \
                      (k == 7 and ((x + y) % 2 + x * y % 3) % 2 == 0)
                if inv:
                    self.m[y][x] = not self.m[y][x]

    def penalita(self) -> int:
        m, n, p = self.m, self.n, 0
        righe = m + [[m[y][x] for y in range(n)] for x in range(n)]
        for riga in righe:
            corsa, prec = 0, None
            for c in riga:                          # file di 5+ moduli uguali
                if c == prec:
                    corsa += 1
                    if corsa == 5:
                        p += 3
                    elif corsa > 5:
                        p += 1
                else:
                    corsa, prec = 1, c
            s = "".join("1" if c else "0" for c in riga)    # finti quadrati di posizione
            for motivo in ("10111010000", "00001011101"):
                p += 40 * sum(1 for i in range(len(s) - 10) if s[i:i + 11] == motivo)
        for y in range(n - 1):                      # blocchi 2×2 dello stesso colore
            for x in range(n - 1):
                c = m[y][x]
                if c == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                    p += 3
        scuri = sum(sum(r) for r in m)
        totale = n * n
        p += ((abs(scuri * 20 - totale * 10) + totale - 1) // totale - 1) * 10   # equilibrio
        return p


def _blocchi(dati: list[int], v: int, livello: str) -> list[int]:
    """Dati divisi in blocchi, correzione Reed-Solomon, poi intercalati."""
    nb, ecc = _BLOCCHI[livello][v], _ECC[livello][v]
    raw = _moduli_dati(v) // 8
    corti = nb - raw % nb
    lung = raw // nb
    div = _rs_divisore(ecc)
    blocchi: list[list[int]] = []
    k = 0
    for i in range(nb):
        dat = dati[k:k + lung - ecc + (0 if i < corti else 1)]
        k += len(dat)
        blocco = dat + _rs_resto(dat, div)
        if i < corti:
            blocco.insert(lung - ecc, 0)            # segnaposto: i blocchi corti hanno un dato in meno
        blocchi.append(blocco)
    out: list[int] = []
    for i in range(len(blocchi[0])):
        for j, b in enumerate(blocchi):
            if i != lung - ecc or j >= corti:
                out.append(b[i])
    return out


def codifica(testo: str, livello: str = "L") -> list[list[bool]]:
    """Matrice del QR più piccolo che contiene `testo`; ValueError se non sta nella versione 10."""
    if livello not in _ECC:
        raise ValueError("livello di correzione: 'L' o 'M'")
    dati = testo.encode("utf-8")
    for v in range(1, MAX_VERSIONE + 1):
        conta = 8 if v <= 9 else 16
        capienza = _codewords_dati(v, livello) * 8
        if 4 + conta + 8 * len(dati) <= capienza:
            break
    else:
        raise ValueError(f"testo troppo lungo per un QR fino alla versione {MAX_VERSIONE}")
    bits: list[int] = []

    def aggiungi(val: int, n: int) -> None:
        bits.extend((val >> i) & 1 for i in reversed(range(n)))

    aggiungi(0b0100, 4)                              # modo byte
    aggiungi(len(dati), conta)
    for b in dati:
        aggiungi(b, 8)
    aggiungi(0, min(4, capienza - len(bits)))
    aggiungi(0, -len(bits) % 8)
    parole = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    riempi = (0xEC, 0x11)
    while len(parole) < capienza // 8:
        parole.append(riempi[(len(parole) - len(bits) // 8) % 2])
    finale = _blocchi(parole, v, livello)
    migliore: tuple[int, list[list[bool]]] | None = None
    for k in range(8):
        q = _Matrice(v)
        q.funzioni()
        q.codewords(finale)
        q.maschera(k)
        q.formato(livello, k)
        p = q.penalita()
        if migliore is None or p < migliore[0]:
            migliore = (p, q.m)
    assert migliore is not None
    return migliore[1]
