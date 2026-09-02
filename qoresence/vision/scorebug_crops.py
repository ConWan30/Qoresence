"""Profile-aware scorebug crop fractions.

CFB OCR bands are the pre-existing hard-coded list (byte-stable).
Madden confirm bands must include the bottom scorebug strip (wordmarks +
digits). A player close-up is never a licensed confirm crop.

2026-09-01 sit (qoresence_f06aa33d2ba4): the 0.82–1.00 primary cut off
above the player huddle and missed the HUD that sat just above it.
Pause-plate fallbacks (mid-frame 0.12–0.55) are player-CU and must not
be used as Madden confirm crops.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

# (x1, x2, y1, y2) normalized. CFB list is byte-stable vs prior _ocr_tokens.
CFB_SCOREBUG_CROPS: tuple[tuple[float, float, float, float], ...] = (
    (0.12, 0.88, 0.78, 0.93),  # primary in-game scorebug (ticker excluded)
    (0.20, 0.80, 0.76, 0.92),  # slightly tighter
    (0.30, 0.70, 0.18, 0.55),  # pause / big center scores (OCR only)
    (0.18, 0.82, 0.12, 0.42),  # wider pause plate (OCR only)
)

# Evidence: 2026-09-01 HDMI — scorebug sat ABOVE the player huddle.
# Prior 0.82–1.00 primary licensed a player-CU as last_confirm.
# Postgame FINISH GAME plate lives at the top (left wordmark+score / right).
# No pause plates — those are mid-frame player CUs.
MADDEN_SCOREBUG_CROPS: tuple[tuple[float, float, float, float], ...] = (
    (0.00, 1.00, 0.68, 1.00),  # primary: HUD above player huddle + field pad
    (0.00, 1.00, 0.82, 1.00),  # prior compact HUD (2026-08-28)
    (0.00, 1.00, 0.86, 1.00),  # MNP / broadcast overlay sits above 0.93
    (0.00, 1.00, 0.93, 1.00),  # measured white-strip fallback
    (0.12, 0.88, 0.00, 0.28),  # postgame FINISH GAME score plate
)

CFB_PRIMARY_SCOREBUG = CFB_SCOREBUG_CROPS[0]
MADDEN_PRIMARY_SCOREBUG = MADDEN_SCOREBUG_CROPS[0]


def is_madden_profile(profile: str | object | None) -> bool:
    return "madden" in str(profile or "").lower()


def scorebug_crops_for_profile(
    profile: str | object | None,
) -> tuple[tuple[float, float, float, float], ...]:
    """Return the OCR crop list. Missing/unknown profile → CFB bands.

    When ``--look-graphs`` crop evidence is on, existing bands may be reordered.
    When ``--learning-edge`` is on, an accepted crop_band constraint may overlay
    the primary band. Both flags off is a no-op (returns the same tuple object).
    """
    if is_madden_profile(profile):
        base = MADDEN_SCOREBUG_CROPS
    else:
        base = CFB_SCOREBUG_CROPS
    try:
        from qoresence.graphs.crop_evidence import licensed_crops

        licensed = licensed_crops(profile, base)
        if licensed is not None:
            return licensed
    except Exception:
        pass
    try:
        from qoresence.agents.learning_edge import overlay_crops

        over = overlay_crops(profile, base)
        if over is not None:
            return over
    except Exception:
        pass
    return base


def primary_scorebug_crop(
    profile: str | object | None,
) -> tuple[float, float, float, float]:
    """Single gameplay crop for VLM / overlay. Unknown → CFB primary."""
    return scorebug_crops_for_profile(profile)[0]


def crop_contains(
    crop: Sequence[float],
    *,
    x: float,
    y: float,
) -> bool:
    x1, x2, y1, y2 = crop
    return x1 <= x <= x2 and y1 <= y <= y2


# Confirm VLM must never send a pause / player-CU plate for Madden or CFB.
_CFB_CONFIRM_SCOREBUG: tuple[tuple[float, float, float, float], ...] = (
    CFB_SCOREBUG_CROPS[0],
    CFB_SCOREBUG_CROPS[1],
)


def confirm_scorebug_bands(
    profile: str | object | None,
) -> tuple[tuple[float, float, float, float], ...]:
    """Bands the confirm VLM may send. No pause plates. Unknown → CFB scorebug."""
    if is_madden_profile(profile):
        return scorebug_crops_for_profile(profile)
    licensed = scorebug_crops_for_profile(profile)
    # Drop inherited pause plates (y1 < 0.60) from CFB confirm.
    confirm = tuple(b for b in licensed if float(b[2]) >= 0.60)
    return confirm if confirm else _CFB_CONFIRM_SCOREBUG


def _luma(arr: Any):
    import numpy as np

    if arr.ndim == 3:
        return (
            0.114 * arr[:, :, 0].astype(np.float32)
            + 0.587 * arr[:, :, 1].astype(np.float32)
            + 0.299 * arr[:, :, 2].astype(np.float32)
        )
    return arr.astype(np.float32)


def _glyph_side_fracs(gray_band: Any) -> tuple[float, float]:
    """Bright *glyph* coverage on the left/right thirds.

    Drops large connected blobs (jersey / helmet). Wordmarks and digits stay.
    """
    import numpy as np

    try:
        import cv2
    except Exception:
        bright = gray_band >= 170.0
        w = int(bright.shape[1])
        return (
            float(bright[:, : max(1, w // 3)].mean()),
            float(bright[:, 2 * w // 3 :].mean()),
        )
    mask = (gray_band >= 170.0).astype(np.uint8)
    h, w = int(mask.shape[0]), int(mask.shape[1])
    n_lbl, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    max_glyph = max(48, int(0.012 * h * w))
    small = np.zeros_like(mask)
    for i in range(1, n_lbl):
        if int(stats[i, cv2.CC_STAT_AREA]) <= max_glyph:
            small[labels == i] = 1
    return (
        float(small[:, : max(1, w // 3)].mean()),
        float(small[:, 2 * w // 3 :].mean()),
    )


def crop_misses_scorebug(crop: Any) -> str | None:
    """Fail-closed: player close-up / empty field is not a licensed confirm crop.

    A Madden/CFB scorebug is a *strip* of small bright glyphs on both the left
    and right (wordmarks + digits). A player CU is a large jersey/helmet blob
    and has no such strip. None = the crop may be a scorebug.
    """
    try:
        import numpy as np
    except Exception:
        return "empty_crop"
    if crop is None:
        return "empty_crop"
    try:
        arr = np.asarray(crop)
    except Exception:
        return "empty_crop"
    if arr.size == 0:
        return "empty_crop"
    if arr.ndim < 2:
        return "tiny_crop"
    h, w = int(arr.shape[0]), int(arr.shape[1])
    if h < 8 or w < 16:
        return "tiny_crop"
    gray = _luma(arr)
    band_h = max(16, int(round(0.22 * h)))
    step = max(8, band_h // 2)
    best_l = 0.0
    best_r = 0.0
    found_strip = False
    for y0 in range(0, max(1, h - band_h + 1), step):
        lf, rf = _glyph_side_fracs(gray[y0 : y0 + band_h])
        if lf > best_l:
            best_l = lf
        if rf > best_r:
            best_r = rf
        if lf >= 0.010 and rf >= 0.010:
            found_strip = True
            break
    if found_strip:
        return None
    # Large mid-frame bright mass without side glyphs → player CU.
    bright = gray >= 170.0
    mf = float(bright[:, w // 3 : 2 * w // 3].mean()) if bright.size else 0.0
    if mf > 0.12:
        return "player_cu_crop"
    if best_l < 0.010 or best_r < 0.010:
        return "no_scorebug_sides"
    return None


def looks_like_scorebug(crop: Any) -> bool:
    return crop_misses_scorebug(crop) is None
