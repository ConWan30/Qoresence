"""Licensed confirm-crop frames for tests that expect a mint.

Gray noise and player close-ups must still refuse. Do not use this helper
to weaken ``crop_misses_scorebug`` or ``confirm_mint_refuse``.
"""

from __future__ import annotations

import numpy as np


def licensed_scorebug_frame(
    h: int = 720,
    w: int = 1280,
    *,
    left: str = "SMU 10",
    right: str = "LOU 14",
) -> np.ndarray:
    """Paint small bright glyphs on both left and right thirds of the CFB band.

    Band is ``y1 >= 0.60`` (not a pause plate). The same strip sits inside
    Madden confirm ``0.68–1.00``, so one fixture licenses both profiles.
    ``crop_misses_scorebug`` on the confirm crop must return None.
    """
    import cv2

    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :] = (16, 20, 14)
    y1, y2 = int(h * 0.78), int(h * 0.93)
    frame[y1:y2, :] = (8, 8, 8)
    # CFB confirm (0.12–0.88, 0.78–0.93): left third ~0.12–0.37, right ~0.63–0.88.
    cv2.putText(
        frame,
        left,
        (int(w * 0.16), int(h * 0.88)),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.2,
        (255, 255, 255),
        3,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        right,
        (int(w * 0.68), int(h * 0.88)),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.2,
        (255, 255, 255),
        3,
        cv2.LINE_AA,
    )
    return frame


def gray_noise_frame(
    h: int = 720,
    w: int = 1280,
    *,
    mean: int = 80,
    jitter: int = 6,
    seed: int = 1,
) -> np.ndarray:
    """Player-CU stand-in: injected VLM JSON on this frame must not mint."""
    rng = np.random.default_rng(seed)
    frame = np.full((h, w, 3), int(mean), dtype=np.uint8)
    frame = np.clip(
        frame.astype(np.int16) + rng.integers(-int(jitter), int(jitter) + 1, size=frame.shape),
        0,
        255,
    )
    return frame.astype(np.uint8)
