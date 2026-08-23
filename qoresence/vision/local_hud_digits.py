"""Local football HUD digit lock — no cloud, no invented scores.

Reads the profile-aware scorebug crop and looks for two large, high-contrast
digit blobs on opposite sides. Used when Paddle/EasyOCR/VLM are offline so
Madden still has a fail-closed lock path.

Never guesses. Returns None unless both sides are independently readable
and the pair is not a down/quarter leak.
"""

from __future__ import annotations

import cv2
import numpy as np

from qoresence.vision.scorebug_crops import is_madden_profile, primary_scorebug_crop


def pair_from_x_values(nums: list[tuple[float, int]]) -> tuple[int, int] | None:
    """Map HUD digits ``(x_frac, value)`` to ``(home, away)``.

    Away is left, home is right. Center band is clock / down / yard line —
    a mid-split of the full Madden bar locked 7-22 from an A 22 marker.
    """
    if not nums:
        return None
    left = [(x, v) for x, v in nums if x < 0.28]
    right = [(x, v) for x, v in nums if x > 0.72]
    if not left or not right:
        return None
    away = sorted(left, key=lambda t: t[0])[-1][1]
    home = sorted(right, key=lambda t: t[0])[0][1]
    from qoresence.vision.scoreboard_extractor import _ScoreStabilizer

    if _ScoreStabilizer._looks_suspicious_pair((home, away)):
        return None
    return int(home), int(away)


def _digit_from_blob(bin_img: np.ndarray) -> int | None:
    """Template-free 0–9 classifier on a binary digit crop (white on black)."""
    h, w = bin_img.shape[:2]
    if h < 8 or w < 4:
        return None
    ink = float(np.count_nonzero(bin_img)) / float(h * w)
    if ink < 0.08 or ink > 0.78:
        return None
    mid_x = w // 2
    mid_y = h // 2
    left = bin_img[:, : max(1, mid_x)]
    right = bin_img[:, mid_x:]
    top = bin_img[: max(1, mid_y), :]
    bot = bin_img[mid_y:, :]
    l_ink = float(np.count_nonzero(left)) / float(left.size)
    r_ink = float(np.count_nonzero(right)) / float(right.size)
    t_ink = float(np.count_nonzero(top)) / float(top.size)
    b_ink = float(np.count_nonzero(bot)) / float(bot.size)

    third = max(1, h // 3)
    bands = [
        float(np.count_nonzero(bin_img[i * third : (i + 1) * third, :]))
        / float(bin_img[i * third : (i + 1) * third, :].size)
        for i in range(3)
    ]
    col_q = max(1, w // 4)
    left_bar = float(np.count_nonzero(bin_img[:, :col_q])) / float(bin_img[:, :col_q].size)
    right_bar = float(np.count_nonzero(bin_img[:, -col_q:])) / float(bin_img[:, -col_q:].size)

    # 1: skinny, ink mostly on one vertical
    aspect = w / float(h)
    if aspect < 0.42 and ink < 0.45 and abs(l_ink - r_ink) > 0.12:
        return 1
    # 0: hollow-ish, both sides + both ends
    if left_bar > 0.28 and right_bar > 0.28 and t_ink > 0.22 and b_ink > 0.22 and 0.22 < ink < 0.55:
        holes = _count_holes(bin_img)
        if holes >= 1:
            return 0
    # 8: two holes, dense
    holes = _count_holes(bin_img)
    if holes >= 2 and ink > 0.28:
        return 8
    if holes == 1 and bands[1] > 0.28 and t_ink > 0.22 and b_ink > 0.22:
        # 4 often has a pocket; 6/9 one hole
        if l_ink > r_ink + 0.08 and bands[0] < bands[2]:
            return 6
        if t_ink > b_ink + 0.06 and r_ink > l_ink:
            return 9
        if aspect > 0.55 and abs(l_ink - r_ink) < 0.12:
            return 0
        return 4 if l_ink > r_ink + 0.05 and bands[1] > 0.2 else 6
    # 7: top-heavy, little bottom
    if t_ink > 0.35 and b_ink < 0.18 and bands[0] > bands[2] + 0.12:
        return 7
    # 3: right-heavy, three bands
    if r_ink > l_ink + 0.1 and min(bands) > 0.12:
        return 3
    # 2: top + mid + bottom, not a hole
    if holes == 0 and bands[0] > 0.2 and bands[2] > 0.2 and bands[1] > 0.12:
        if t_ink > 0.25 and b_ink > 0.22:
            return 2
        if l_ink > r_ink and bands[2] > 0.22:
            return 5
    if holes == 0 and l_ink > r_ink + 0.08 and bands[1] > 0.18:
        return 5
    return None


def _count_holes(bin_img: np.ndarray) -> int:
    inv = cv2.bitwise_not(bin_img)
    n, _labels, stats, _ = cv2.connectedComponentsWithStats(inv, connectivity=8)
    h, w = bin_img.shape[:2]
    holes = 0
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if area < 8:
            continue
        touches = x <= 1 or y <= 1 or x + bw >= w - 1 or y + bh >= h - 1
        if not touches:
            holes += 1
    return holes


def _read_side(bin_full: np.ndarray, x0: int, x1: int) -> int | None:
    sl = bin_full[:, max(0, x0) : min(bin_full.shape[1], x1)]
    if sl.size == 0:
        return None
    n, labels, stats, _ = cv2.connectedComponentsWithStats(sl, connectivity=8)
    blobs: list[tuple[int, int]] = []
    for i in range(1, n):
        _x, _y, bw, bh, area = stats[i]
        if area < 18 or bh < sl.shape[0] * 0.35 or bw < 3:
            continue
        if bh / max(1, bw) < 0.7:
            continue
        crop = sl[_y : _y + bh, _x : _x + bw]
        d = _digit_from_blob(crop)
        if d is None:
            continue
        blobs.append((d, _x))
    if not blobs:
        return None
    blobs.sort(key=lambda t: t[1])
    if len(blobs) == 1:
        return blobs[0][0]
    # two-digit score: most-left is tens
    tens, ones = blobs[0][0], blobs[1][0]
    val = tens * 10 + ones
    if 0 <= val <= 99:
        return val
    return None


def _numbers_across(bin_full: np.ndarray) -> list[tuple[float, int]]:
    """Classify digit blobs left→right and glue adjacent pairs into 1–2 digit scores."""
    h, w = bin_full.shape[:2]
    n, _labels, stats, _ = cv2.connectedComponentsWithStats(bin_full, connectivity=8)
    digits: list[tuple[int, int, int]] = []
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if area < 18 or bh < h * 0.35 or bw < 3:
            continue
        if bh / max(1, bw) < 0.7:
            continue
        crop = bin_full[y : y + bh, x : x + bw]
        d = _digit_from_blob(crop)
        if d is None:
            continue
        digits.append((d, x, x + bw))
    digits.sort(key=lambda t: t[1])
    nums: list[tuple[float, int]] = []
    i = 0
    while i < len(digits):
        d0, x0, x1 = digits[i]
        if i + 1 < len(digits) and (digits[i + 1][1] - x1) < w * 0.03:
            val = d0 * 10 + digits[i + 1][0]
            cx = (x0 + digits[i + 1][2]) / 2.0 / float(w)
            nums.append((cx, val))
            i += 2
            continue
        nums.append(((x0 + x1) / 2.0 / float(w), d0))
        i += 1
    return nums


def read_score_pair(
    frame: np.ndarray, profile: str | object | None = None
) -> tuple[int, int] | None:
    """Return (home, away) or None. Away is left, home is right (ops convention)."""
    if frame is None or getattr(frame, "size", 0) == 0 or len(frame.shape) < 2:
        return None
    h, w = int(frame.shape[0]), int(frame.shape[1])
    if h < 80 or w < 160:
        return None
    x1f, x2f, y1f, y2f = primary_scorebug_crop(profile)
    x1, x2 = int(w * x1f), int(w * x2f)
    y1, y2 = int(h * y1f), int(h * y2f)
    if y2 - y1 < 8 or x2 - x1 < 40:
        return None
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
    # HUD digits are usually bright on a dark/translucent bar
    _t, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if float(np.mean(binary)) > 127:
        binary = cv2.bitwise_not(binary)
    if is_madden_profile(profile):
        return pair_from_x_values(_numbers_across(binary))
    ch, cw = binary.shape[:2]
    mid = cw // 2
    pad = max(4, cw // 12)
    away = _read_side(binary, 0, mid - pad)
    home = _read_side(binary, mid + pad, cw)
    if away is None or home is None:
        return None
    if (home, away) == (0, 0):
        # Kickoff 0-0 is legal, but also the empty-bar failure mode.
        # Require enough ink on both halves to accept a shutout open.
        left_ink = float(np.mean(binary[:, :mid]))
        right_ink = float(np.mean(binary[:, mid:]))
        if left_ink < 12 or right_ink < 12:
            return None
    from qoresence.vision.scoreboard_extractor import _ScoreStabilizer

    if _ScoreStabilizer._looks_suspicious_pair((home, away)):
        return None
    return int(home), int(away)
