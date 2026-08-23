"""Profile-aware scorebug crop fractions.

CFB bands are the pre-existing hard-coded list (unchanged).
Madden bands are derived from preexisting 2026-08-14/15 frames only:
the white full-width HUD strip measures y=0.9361–0.9375 .. 1.00
(1280x720 stills and 640x360 clip frames). Unknown profile → CFB.
"""

from __future__ import annotations

from collections.abc import Sequence

# (x1, x2, y1, y2) normalized. CFB list is byte-stable vs prior _ocr_tokens.
CFB_SCOREBUG_CROPS: tuple[tuple[float, float, float, float], ...] = (
    (0.12, 0.88, 0.78, 0.93),  # primary in-game scorebug (ticker excluded)
    (0.20, 0.80, 0.76, 0.92),  # slightly tighter
    (0.30, 0.70, 0.18, 0.55),  # pause / big center scores
    (0.18, 0.82, 0.12, 0.42),  # wider pause plate
)

# Evidence: eye_check_80093078000000 / 77134656000000 + late 20260814 clips.
# White HUD bar starts at y≈0.9375 (720p) / 0.9361 (360p) and runs to 1.00.
# y1=0.93 is a 3–4 px pad above the measured edge so glyphs are not clipped.
# Pause crops are inherited CFB fallbacks (no Madden pause-score plate measured).
MADDEN_SCOREBUG_CROPS: tuple[tuple[float, float, float, float], ...] = (
    (0.00, 1.00, 0.93, 1.00),  # primary white HUD strip (full width)
    (0.00, 1.00, 0.92, 1.00),  # 1% pad (one clip row measured 0.9167)
    (0.00, 1.00, 0.86, 1.00),  # MNP / broadcast overlay sits above 0.93
    (0.30, 0.70, 0.18, 0.55),  # inherited pause fallback
    (0.18, 0.82, 0.12, 0.42),  # inherited wider pause fallback
)

CFB_PRIMARY_SCOREBUG = CFB_SCOREBUG_CROPS[0]
MADDEN_PRIMARY_SCOREBUG = MADDEN_SCOREBUG_CROPS[0]


def is_madden_profile(profile: str | object | None) -> bool:
    return "madden" in str(profile or "").lower()


def scorebug_crops_for_profile(
    profile: str | object | None,
) -> tuple[tuple[float, float, float, float], ...]:
    """Return the OCR crop list. Missing/unknown profile → CFB bands."""
    if is_madden_profile(profile):
        return MADDEN_SCOREBUG_CROPS
    return CFB_SCOREBUG_CROPS


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
