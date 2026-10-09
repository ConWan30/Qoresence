"""Glyph primitives for the local scorebug reader (numpy + OpenCV only).

Everything here works on small crops already scaled to the profile's
reference size (640x360 for Madden). No I/O, no globals, no network.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# Normalised glyph size (w, h) used for every template group.
GLYPH_SIZE: tuple[int, int] = (10, 14)


@dataclass(frozen=True)
class GlyphMatch:
    label: str
    best: float
    second: float

    @property
    def margin(self) -> float:
        return float(self.best - self.second)


def norm_vec(patch: np.ndarray, size: tuple[int, int] = GLYPH_SIZE) -> np.ndarray | None:
    """Resize a glyph patch, zero-mean it, L2-normalise it. None when flat."""
    if patch is None or patch.size == 0 or patch.shape[0] < 2 or patch.shape[1] < 1:
        return None
    arr = patch.astype(np.float32)
    if arr.max() > 1.0:
        arr = arr / 255.0
    v = cv2.resize(arr, size, interpolation=cv2.INTER_AREA).ravel().astype(np.float32)
    v = v - float(v.mean())
    n = float(np.linalg.norm(v))
    if n < 1e-6:
        return None
    return v / n


def hole_signature(mask: np.ndarray) -> str:
    """Topology of one binary glyph: number of enclosed holes and where they sit.

    Returns ``"0"`` (no hole), ``"1u"``/``"1c"``/``"1l"`` (one hole above, across
    or below the glyph's vertical middle) or ``"2+"``. Template matching alone
    cannot tell an unseen 8 from a 0 at 640x360 (both are a dark oval); an 8 has
    two holes, or one hole that does not cross the middle row, so this check
    makes it blank instead of reading as another digit.
    """
    ink = (np.asarray(mask) > 0).astype(np.uint8)
    if ink.size == 0:
        return "0"
    # Background pixels not 4-connected to the border are holes (ink is 8-connected).
    bg = np.pad(1 - ink, 1, constant_values=1)
    n, lab = cv2.connectedComponents(bg, connectivity=4)
    outside = lab[0, 0]
    rows = [np.nonzero((lab == k).any(axis=1))[0] - 1 for k in range(1, n) if k != outside]
    if not rows:
        return "0"
    if len(rows) >= 2:
        return "2+"
    centre = (ink.shape[0] - 1) / 2.0
    top, bottom = int(rows[0].min()), int(rows[0].max())
    if bottom < centre:
        return "1u"
    if top > centre:
        return "1l"
    return "1c"


def dark_on_light_ink(bgr: np.ndarray) -> np.ndarray:
    """Madden white strip: team-coloured or dark digits on a near-white strip."""
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    s = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[..., 1]
    ink = ((g < 165) | (s > 90)) & ~((g > 200) & (s < 40))
    return ink.astype(np.uint8) * 255


def light_on_dark_ink(bgr: np.ndarray, floor: int = 70) -> np.ndarray:
    """White or red text on the dark clock box: threshold the HSV value channel."""
    v = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[..., 2]
    if v.size == 0:
        return np.zeros(v.shape, np.uint8)
    thr, _ = cv2.threshold(v, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    thr = max(float(thr), float(floor))
    return ((v > thr).astype(np.uint8)) * 255


def value_channel(bgr: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[..., 2]


def components(
    mask: np.ndarray,
    *,
    min_h: int,
    max_h: int,
    min_area: int,
    split_w: int,
    max_w: int,
) -> list[tuple[int, int, int, int]]:
    """Digit-height connected components, left to right.

    Blobs wider than ``split_w`` are treated as two touching digits and split
    at the emptiest column in their middle third. Anything wider than
    ``max_w`` or outside the height band is dropped (the caller then sees a
    glyph count it does not expect and blanks).
    """
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    out: list[tuple[int, int, int, int]] = []
    for i in range(1, n):
        x, y, w, h, a = (int(t) for t in st[i])
        if h < min_h or a < min_area:
            continue
        if h > max_h or w > max_w:
            # Too big to be a digit: a banner, a logo, a slide-in edge.
            out.append((x, y, -1, h))
            continue
        if w > split_w:
            colsum = (lab[y : y + h, x : x + w] == i).sum(0)
            lo, hi = w // 3, 2 * w // 3 + 1
            cut = lo + int(colsum[lo:hi].argmin())
            out += [(x, y, cut, h), (x + cut, y, w - cut, h)]
            continue
        out.append((x, y, w, h))
    return sorted(out)


def column_runs(mask: np.ndarray, min_ink: int = 1) -> list[tuple[int, int]]:
    """[x0, x1) runs of columns that carry ink."""
    cols = (mask > 0).sum(0)
    runs: list[tuple[int, int]] = []
    start = None
    for x, c in enumerate(cols):
        if c >= min_ink and start is None:
            start = x
        elif c < min_ink and start is not None:
            runs.append((start, x))
            start = None
    if start is not None:
        runs.append((start, int(mask.shape[1])))
    return runs


def match(vec: np.ndarray, templates: dict[str, np.ndarray]) -> GlyphMatch | None:
    """Best and runner-up normalised cross-correlation against a template set."""
    if vec is None or not templates:
        return None
    scores = sorted(((float(vec @ t), k) for k, t in templates.items()), reverse=True)
    best, label = scores[0]
    second = scores[1][0] if len(scores) > 1 else -1.0
    return GlyphMatch(label=label, best=best, second=second)


def ncc(a: np.ndarray, b: np.ndarray) -> float:
    """Zero-mean normalised cross-correlation of two same-shape patches."""
    x = a.astype(np.float32).ravel()
    y = b.astype(np.float32).ravel()
    x = x - x.mean()
    y = y - y.mean()
    d = float(np.linalg.norm(x) * np.linalg.norm(y))
    if d < 1e-6:
        return 0.0
    return float(x @ y) / d
