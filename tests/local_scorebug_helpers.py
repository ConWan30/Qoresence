"""Shared helpers for the local scorebug tests (fixtures are 640x30 band crops)."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "local_scorebug"


def band(name: str) -> np.ndarray:
    img = cv2.imread(str(FIXTURES / f"{name}.jpg"))
    assert img is not None, name
    assert img.shape == (30, 640, 3)
    return img


def frame_from_band(
    name_or_band: str | np.ndarray, size: tuple[int, int] = (640, 360)
) -> np.ndarray:
    """Paste a fixture band at the bottom of a 640x360 field-green frame, then scale."""
    b = band(name_or_band) if isinstance(name_or_band, str) else name_or_band
    frame = np.full((360, 640, 3), (40, 90, 40), np.uint8)
    frame[330:] = b
    if size != (640, 360):
        frame = cv2.resize(frame, size, interpolation=cv2.INTER_CUBIC)
    return frame
