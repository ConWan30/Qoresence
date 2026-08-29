"""Profile-aware scorebug crops — CFB unchanged, Madden from preexisting frames."""

from __future__ import annotations

import numpy as np

from qoresence.vision.scoreboard_vlm import ScoreboardVlmReferee
from qoresence.vision.scorebug_crops import (
    CFB_PRIMARY_SCOREBUG,
    CFB_SCOREBUG_CROPS,
    MADDEN_PRIMARY_SCOREBUG,
    MADDEN_SCOREBUG_CROPS,
    crop_contains,
    primary_scorebug_crop,
    scorebug_crops_for_profile,
)


def test_cfb_bands_unchanged():
    assert CFB_SCOREBUG_CROPS == (
        (0.12, 0.88, 0.78, 0.93),
        (0.20, 0.80, 0.76, 0.92),
        (0.30, 0.70, 0.18, 0.55),
        (0.18, 0.82, 0.12, 0.42),
    )


def test_unknown_and_ncaa_use_cfb():
    assert scorebug_crops_for_profile(None) is CFB_SCOREBUG_CROPS
    assert scorebug_crops_for_profile("") is CFB_SCOREBUG_CROPS
    assert scorebug_crops_for_profile("ncaa_football_27") is CFB_SCOREBUG_CROPS
    assert scorebug_crops_for_profile("unknown") is CFB_SCOREBUG_CROPS
    assert primary_scorebug_crop(None) == CFB_PRIMARY_SCOREBUG


def test_madden_uses_evidence_bands():
    assert scorebug_crops_for_profile("madden_27") is MADDEN_SCOREBUG_CROPS
    assert scorebug_crops_for_profile("Madden") is MADDEN_SCOREBUG_CROPS
    assert primary_scorebug_crop("madden_27") == MADDEN_PRIMARY_SCOREBUG
    # Measured HUD centroid (y=0.97, x=0.5) is inside Madden primary, outside CFB.
    assert crop_contains(MADDEN_PRIMARY_SCOREBUG, x=0.50, y=0.97)
    assert not crop_contains(CFB_PRIMARY_SCOREBUG, x=0.50, y=0.97)
    # CFB scorebug centroid stays in CFB primary, not Madden primary.
    assert crop_contains(CFB_PRIMARY_SCOREBUG, x=0.50, y=0.85)
    assert not crop_contains(MADDEN_PRIMARY_SCOREBUG, x=0.50, y=0.85)


def test_madden_primary_is_full_width_bottom_strip():
    x1, x2, y1, y2 = MADDEN_PRIMARY_SCOREBUG
    assert x1 == 0.0 and x2 == 1.0
    assert y1 == 0.93 and y2 == 1.0


def test_vlm_default_crop_still_excludes_ticker():
    h, w = 100, 200
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[int(h * 0.93) :, :, 2] = 255
    frame[int(h * 0.78) : int(h * 0.93), :, 1] = 255
    crop = ScoreboardVlmReferee._crop(frame, game_state="gameplay")
    assert crop is not None
    assert int(crop[:, :, 2].max()) == 0
    assert int(crop[:, :, 1].max()) == 255


def test_vlm_madden_crop_takes_bottom_strip():
    # Real stills are 720p; a 100px canvas makes the 0.93-1.00 strip <8px
    # and the VLM slicer (unchanged) rejects it.
    h, w = 720, 1280
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    # CFB band green; Madden HUD strip blue
    frame[int(h * 0.78) : int(h * 0.93), :, 1] = 255
    frame[int(h * 0.93) :, :, 0] = 255
    crop = ScoreboardVlmReferee._crop(frame, game_state="gameplay", game_profile="madden_27")
    assert crop is not None
    assert int(crop[:, :, 0].max()) == 255
    assert int(crop[:, :, 1].max()) == 0


def test_vlm_madden_menu_still_uses_hud_crop():
    """Madden profile + game_state='menu' must still crop the bottom HUD, not center pause plate.
    
    Regression test for 2026-08-29 bug: live Madden gameplay had game_state wrongly
    classified as 'menu', causing VLM to crop the center field (0.12–0.52 y) instead
    of the bottom HUD (0.93–1.00 y) where the scorebug actually is.
    """
    h, w = 720, 1280
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    # Pause plate region (center): red channel
    frame[int(h * 0.12) : int(h * 0.52), int(w * 0.22) : int(w * 0.78), 2] = 255
    # Madden HUD strip (bottom): blue channel
    frame[int(h * 0.93) :, :, 0] = 255
    
    crop = ScoreboardVlmReferee._crop(frame, game_state="menu", game_profile="madden_27")
    assert crop is not None
    # Must contain blue (HUD), not red (pause plate)
    assert int(crop[:, :, 0].max()) == 255, "Madden menu crop must include bottom HUD (blue)"
    assert int(crop[:, :, 2].max()) == 0, "Madden menu crop must NOT include center pause plate (red)"
