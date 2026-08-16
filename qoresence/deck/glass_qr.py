"""Minimal QR (byte mode, ECC L) for Mobile Glass URLs. No CDN, no extra dep."""

from __future__ import annotations

# Version 1-6, ECC L: (size, data_cw, ec_cw, align_centers)
_VER = {
    1: (21, 19, 7, ()),
    2: (25, 34, 10, (18,)),
    3: (29, 55, 15, (22,)),
    4: (33, 80, 20, (26,)),
    5: (37, 108, 26, (30,)),
    6: (41, 136, 18, (34,)),
}

# GF(256) for Reed-Solomon
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for i in range(255):
    _EXP[i] = _x
    _LOG[_x] = i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for i in range(255, 512):
    _EXP[i] = _EXP[i - 255]


def _gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _rs_poly(ec: int) -> list[int]:
    poly = [1]
    for i in range(ec):
        nxt = [0] * (len(poly) + 1)
        for j, c in enumerate(poly):
            nxt[j] ^= _gf_mul(c, _EXP[i])
            nxt[j + 1] ^= c
        poly = nxt
    return poly


def _rs_ec(data: list[int], ec: int) -> list[int]:
    gen = _rs_poly(ec)
    msg = data + [0] * ec
    for i in range(len(data)):
        coef = msg[i]
        if coef == 0:
            continue
        for j in range(1, len(gen)):
            msg[i + j] ^= _gf_mul(gen[j], coef)
    return msg[-ec:]


def _bits_to_cw(bits: str, n: int) -> list[int]:
    bits = bits + "0" * ((8 - len(bits) % 8) % 8)
    pad = bytes([0xEC, 0x11])
    out: list[int] = []
    i = 0
    while len(out) < n:
        if i < len(bits):
            out.append(int(bits[i : i + 8], 2))
            i += 8
        else:
            out.append(pad[(len(out) - i // 8) % 2])
    return out[:n]


def _choose_ver(n: int) -> int:
    for v, (_s, data_cw, _ec, _al) in _VER.items():
        # mode(4)+count(8)+data+terminator
        cap = data_cw - 2
        if n <= cap:
            return v
    raise ValueError("URL too long for glass QR")


def _reserve(size: int, ver: int) -> list[list[int]]:
    """-1 empty, 0/1 reserved/data later. 2 = reserved (do not mask)."""
    m = [[-1] * size for _ in range(size)]

    def fill(r: int, c: int, rows: int, cols: int, val: int) -> None:
        for y in range(r, r + rows):
            for x in range(c, c + cols):
                if 0 <= y < size and 0 <= x < size:
                    m[y][x] = val

    def finder(r: int, c: int) -> None:
        fill(r - 1, c - 1, 9, 9, 0)
        fill(r, c, 7, 7, 1)
        fill(r + 1, c + 1, 5, 5, 0)
        fill(r + 2, c + 2, 3, 3, 1)

    finder(0, 0)
    finder(0, size - 7)
    finder(size - 7, 0)
    for i in range(8):
        if m[i][8] == -1:
            m[i][8] = 2
        if m[8][i] == -1:
            m[8][i] = 2
        if m[size - 1 - i][8] == -1:
            m[size - 1 - i][8] = 2
        if m[8][size - 1 - i] == -1:
            m[8][size - 1 - i] = 2
    m[8][8] = 2
    for i in range(8, size - 8):
        m[6][i] = 1 if (i % 2 == 0) else 0
        m[i][6] = 1 if (i % 2 == 0) else 0
    for c in _VER[ver][3]:
        for r in _VER[ver][3]:
            if m[r][c] != -1:
                continue
            fill(r - 2, c - 2, 5, 5, 0)
            fill(r - 1, c - 1, 3, 3, 1)
            m[r][c] = 0
    return m


def _place(m: list[list[int]], data: list[int]) -> None:
    size = len(m)
    bits: list[int] = []
    for b in data:
        for k in range(7, -1, -1):
            bits.append((b >> k) & 1)
    i = 0
    up = True
    col = size - 1
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(size - 1, -1, -1) if up else range(size)
        for r in rows:
            for c in (col, col - 1):
                if m[r][c] == -1:
                    m[r][c] = bits[i] if i < len(bits) else 0
                    i += 1
        up = not up
        col -= 2


def _mask_fn(k: int):
    fns = (
        lambda r, c: (r + c) % 2 == 0,
        lambda r, c: r % 2 == 0,
        lambda r, c: c % 3 == 0,
        lambda r, c: (r + c) % 3 == 0,
        lambda r, c: (r // 2 + c // 3) % 2 == 0,
        lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
        lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
        lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
    )
    return fns[k]


def _apply_mask(m: list[list[int]], reserved: list[list[bool]], k: int) -> list[list[int]]:
    fn = _mask_fn(k)
    size = len(m)
    out = [row[:] for row in m]
    for r in range(size):
        for c in range(size):
            if not reserved[r][c] and fn(r, c):
                out[r][c] ^= 1
    return out


def _format_bits(mask: int) -> int:
    # ECC L = 01, then 3-bit mask. BCH(15,5)
    data = (0b01 << 3) | mask
    rem = data << 10
    gen = 0b10100110111
    for i in range(14, 9, -1):
        if rem & (1 << i):
            rem ^= gen << (i - 10)
    bits = ((data << 10) | rem) ^ 0x5412
    return bits


def _draw_format(m: list[list[int]], mask: int) -> None:
    bits = _format_bits(mask)
    size = len(m)
    pos_a = [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
             (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)]
    pos_b = [(size - 1, 8), (size - 2, 8), (size - 3, 8), (size - 4, 8), (size - 5, 8),
             (size - 6, 8), (size - 7, 8), (8, size - 8), (8, size - 7), (8, size - 6),
             (8, size - 5), (8, size - 4), (8, size - 3), (8, size - 2), (8, size - 1)]
    for i, (r, c) in enumerate(pos_a):
        m[r][c] = (bits >> (14 - i)) & 1
    for i, (r, c) in enumerate(pos_b):
        m[r][c] = (bits >> (14 - i)) & 1
    m[size - 8][8] = 1  # dark module


def encode_modules(text: str) -> list[list[int]]:
    raw = text.encode("utf-8")
    ver = _choose_ver(len(raw))
    size, data_cw, ec_cw, _al = _VER[ver]
    bits = "0100" + f"{len(raw):08b}" + "".join(f"{b:08b}" for b in raw) + "0000"
    data = _bits_to_cw(bits, data_cw)
    data = data + _rs_ec(data, ec_cw)
    reserved_map = _reserve(size, ver)
    reserved = [[cell != -1 for cell in row] for row in reserved_map]
    work = [row[:] for row in reserved_map]
    for r in range(size):
        for c in range(size):
            if work[r][c] == 2:
                work[r][c] = 0
    _place(work, data)
    best = None
    best_k = 0
    best_score = 10**9
    for k in range(8):
        masked = _apply_mask(work, reserved, k)
        _draw_format(masked, k)
        score = sum(sum(row) for row in masked)
        # light penalty: prefer mid density
        score = abs(score - (size * size) // 2)
        if score < best_score:
            best_score = score
            best_k = k
            best = masked
    assert best is not None
    _draw_format(best, best_k)
    return best


def modules_to_svg(mod: list[list[int]], scale: int = 8, quiet: int = 4) -> str:
    n = len(mod)
    dim = (n + quiet * 2) * scale
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {dim} {dim}" '
        f'width="{dim}" height="{dim}" shape-rendering="crispEdges">'
        f'<rect width="100%" height="100%" fill="#fff"/>'
    ]
    for r, row in enumerate(mod):
        for c, v in enumerate(row):
            if v:
                x = (c + quiet) * scale
                y = (r + quiet) * scale
                parts.append(f'<rect x="{x}" y="{y}" width="{scale}" height="{scale}" fill="#000"/>')
    parts.append("</svg>")
    return "".join(parts)


def url_to_svg(url: str) -> str:
    return modules_to_svg(encode_modules(url))
