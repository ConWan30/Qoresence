"""Optical CFB markers — ticker/logo text when game_title is null.

Bottom-left ticker strip often reads ``EA SPORTS COLLEGE FOOTBALL 27`` on CFB
HUD even when the operator seed/pin is ``madden_27`` and ``game_title`` is empty.
"""

from __future__ import annotations

import re
import threading
from typing import Any

import numpy as np

# Match scoreboard_vlm ticker cut (y > 0.93).
_TICKER_CUT_Y = 0.93

# Operator / optical ticker strings (case-insensitive).
CFB_OPTICAL_RE = re.compile(r"college\s*football|\bcfb\b|\bncaa\b", re.IGNORECASE)

# Bottom-left logo + product string (y > TICKER_CUT_Y).
TICKER_STRIP_FRAC = (0.0, 0.55, _TICKER_CUT_Y, 1.0)

_hint_lock = threading.Lock()
_hint_profile: str | None = None
_hint_title: str | None = None
_locked_title: str | None = None
_locked_optical_profile: str | None = None
_last_ticker_text: str = ""


def cfb_markers_in_text(text: str | None) -> bool:
    return bool(text and CFB_OPTICAL_RE.search(str(text)))


def is_cfb_profile_id(profile_id: Any) -> bool:
    p = str(profile_id or "").lower()
    return any(m in p for m in ("cfb", "college", "ncaa"))


def cfb_markers_in_profile_or_title(
    game_profile: str | None = None,
    game_title: str | None = None,
) -> bool:
    profile_lower = str(game_profile or "").lower()
    title_lower = str(game_title or "").lower()
    markers = ("cfb", "college", "ncaa", "college football")
    return any(m in profile_lower or m in title_lower for m in markers)


def slice_ticker_strip(frame: np.ndarray) -> np.ndarray | None:
    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    h, w = frame.shape[:2]
    if h < 40 or w < 40:
        return None
    x1f, x2f, y1f, y2f = TICKER_STRIP_FRAC
    x1, x2 = int(w * x1f), int(w * x2f)
    y1, y2 = int(h * y1f), int(h * y2f)
    if y2 <= y1 or x2 <= x1:
        return None
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    return crop


def read_ticker_strip_text(frame: np.ndarray) -> str:
    """OCR the bottom-left ticker/logo strip. Empty when engine is not ready."""
    import os

    if os.environ.get("QORESENCE_DISABLE_SCOREBOARD_OCR", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        return ""
    if os.environ.get("QORESENCE_EASY_OCR", "0").strip().lower() not in {
        "1",
        "true",
        "yes",
    }:
        return ""
    crop = slice_ticker_strip(frame)
    if crop is None:
        return ""
    try:
        import cv2

        from qoresence.vision.scoreboard_ocr_engine import get_scoreboard_engine

        eng = get_scoreboard_engine()
        if not eng.is_ready():
            eng.start_warmup()
            return ""
        variants = [crop]
        try:
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            variants.append(cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR))
        except Exception:
            pass
        parts: list[str] = []
        for variant in variants:
            for box in eng.read_boxes(variant):
                text = str(getattr(box, "text", "") or "").strip()
                if text:
                    parts.append(text)
        return " ".join(parts)
    except Exception:
        return ""


def frame_has_cfb_optical_markers(
    frame: np.ndarray | None,
    *,
    game_profile: str | None = None,
    game_title: str | None = None,
) -> bool:
    """True when profile/title or ticker/logo OCR shows CFB markers."""
    global _last_ticker_text
    if cfb_markers_in_profile_or_title(game_profile, game_title):
        return True
    if frame is None or getattr(frame, "size", 0) == 0:
        return False
    ticker_text = read_ticker_strip_text(frame)
    _last_ticker_text = ticker_text
    return cfb_markers_in_text(ticker_text)


def last_ticker_strip_text() -> str:
    return _last_ticker_text


def stash_locked_optical_title(title: str | None, profile: str | None = None) -> None:
    """Remember HYST_LOCKED title/profile for mid-drive confirm crop."""
    global _locked_title, _locked_optical_profile
    with _hint_lock:
        if title:
            _locked_title = str(title)
        if profile:
            _locked_optical_profile = "cfb_27" if is_cfb_profile_id(profile) else str(profile)


def locked_optical_title() -> tuple[str | None, str | None]:
    with _hint_lock:
        return _locked_title, _locked_optical_profile


def stamp_confirm_context(ctx: Any, frame: np.ndarray | None) -> None:
    """Before extract/schedule: stamp empty ctx title/profile for CFB crop."""
    if ctx is None:
        return
    existing_title = getattr(ctx, "game_title", None)
    if existing_title:
        try:
            from qoresence.core.unified_config import GameProfileId, profile_from_title

            if profile_from_title(existing_title) == GameProfileId.MADDEN_27:
                return
        except Exception:
            pass

    locked_title, locked_profile = locked_optical_title()
    hint_profile, hint_title = football_confirm_hint()
    title = existing_title or locked_title or hint_title
    if title and not existing_title:
        ctx.game_title = title
    scan_profile = getattr(ctx, "game_profile", None) or hint_profile
    if frame is not None and frame_has_cfb_optical_markers(
        frame,
        game_profile=scan_profile,
        game_title=title,
    ):
        ctx.game_profile = "cfb_27"
        set_football_confirm_hint("cfb_27", title)
        return
    if is_cfb_profile_id(locked_profile) and not existing_title:
        try:
            from qoresence.core.unified_config import GameProfileId, profile_from_title

            if title and profile_from_title(title) == GameProfileId.CFB_27:
                ctx.game_profile = "cfb_27"
                set_football_confirm_hint("cfb_27", title)
        except Exception:
            ctx.game_profile = "cfb_27"
            set_football_confirm_hint("cfb_27", title)


def set_football_confirm_hint(profile: str | None, title: str | None = None) -> None:
    global _hint_profile, _hint_title
    with _hint_lock:
        if profile:
            _hint_profile = str(profile)
        if title:
            _hint_title = str(title)


def football_confirm_hint() -> tuple[str | None, str | None]:
    with _hint_lock:
        return _hint_profile, _hint_title


def clear_football_confirm_hint() -> None:
    global _hint_profile, _hint_title, _last_ticker_text, _locked_title, _locked_optical_profile
    with _hint_lock:
        _hint_profile = None
        _hint_title = None
        _locked_title = None
        _locked_optical_profile = None
    _last_ticker_text = ""
