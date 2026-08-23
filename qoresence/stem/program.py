"""Stem Program-out — Monitor options. FrameHub stay clean; HUD is blit-only."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StemProgramOptions:
    display_index: int = 0
    fullscreen: bool = True
    burn_hud: bool = True
    origin_x: int = 0
    origin_y: int = 0


def program_options(
    *,
    display_index: int = 0,
    fullscreen: bool = True,
    burn_hud: bool = True,
    origin_x: int | None = None,
    origin_y: int | None = None,
) -> StemProgramOptions:
    """Map display index to a window origin. Does not open capture."""
    dx = max(0, int(display_index))
    ox = int(origin_x) if origin_x is not None else dx * 1920
    oy = int(origin_y) if origin_y is not None else 0
    return StemProgramOptions(
        display_index=dx,
        fullscreen=bool(fullscreen),
        burn_hud=bool(burn_hud),
        origin_x=ox,
        origin_y=oy,
    )


def apply_program_window(cv2: object, window_title: str, opts: StemProgramOptions) -> None:
    """Position / fullscreen an existing HighGUI window. FrameHub is not touched."""
    move = getattr(cv2, "moveWindow", None)
    if callable(move):
        try:
            move(window_title, int(opts.origin_x), int(opts.origin_y))
        except Exception:
            pass
    if opts.fullscreen:
        prop = getattr(cv2, "setWindowProperty", None)
        full = getattr(cv2, "WND_PROP_FULLSCREEN", None)
        mode = getattr(cv2, "WINDOW_FULLSCREEN", 1)
        if callable(prop) and full is not None:
            try:
                prop(window_title, full, mode)
            except Exception:
                pass
