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
    # Compact HUD + white-strip centroid are inside Madden primary, outside CFB.
    assert crop_contains(MADDEN_PRIMARY_SCOREBUG, x=0.50, y=0.97)
    assert crop_contains(MADDEN_PRIMARY_SCOREBUG, x=0.50, y=0.88)
    # HUD that sat above the player huddle (2026-09-01 sit) is now inside primary.
    assert crop_contains(MADDEN_PRIMARY_SCOREBUG, x=0.50, y=0.72)
    assert not crop_contains(CFB_PRIMARY_SCOREBUG, x=0.50, y=0.97)
    # CFB scorebug centroid stays in CFB primary.
    assert crop_contains(CFB_PRIMARY_SCOREBUG, x=0.50, y=0.85)
    # Mid-field is not a Madden HUD.
    assert not crop_contains(MADDEN_PRIMARY_SCOREBUG, x=0.50, y=0.50)


def test_madden_primary_is_full_width_readable_hud():
    x1, x2, y1, y2 = MADDEN_PRIMARY_SCOREBUG
    assert x1 == 0.0 and x2 == 1.0
    assert y1 == 0.68 and y2 == 1.0
    # Pause / player-CU plates must not be Madden confirm bands.
    for band in MADDEN_SCOREBUG_CROPS:
        assert float(band[2]) < 0.60 or float(band[2]) >= 0.68
        assert not (0.12 <= float(band[2]) <= 0.55 and 0.18 <= float(band[3]) <= 0.55)


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


def test_madden_360p_crop_is_tall_enough_for_vlm():
    """640×360 Madden HUD must not be sent as a ~26px ticker strip."""
    h, w = 360, 640
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[int(h * 0.93) :, :, 0] = 200
    frame[int(h * 0.82) : int(h * 0.93), :, 1] = 40
    crop = ScoreboardVlmReferee._crop(frame, game_state="gameplay", game_profile="madden_27")
    assert crop is not None
    assert crop.shape[0] >= 96
    assert int(crop[:, :, 0].max()) >= 150


def test_choice_text_prefers_reasoning_json_when_content_empty():
    text, finish = ScoreboardVlmReferee._choice_text(
        {
            "finish_reason": "length",
            "message": {
                "role": "assistant",
                "content": "",
                "reasoning_content": 'scratch\n{"home_score": 0, "away_score": 3}',
            },
        }
    )
    assert finish == "length"
    assert "home_score" in text
    parsed = ScoreboardVlmReferee._parse_json(text)
    assert parsed is not None
    assert parsed["home_score"] == 0
    assert parsed["away_score"] == 3


def test_parse_json_keeps_visible_control():
    parsed = ScoreboardVlmReferee._parse_json(
        '{"home_score": 0, "away_score": 10, "left_team": "SF", "right_team": "LV",'
        ' "clock": "2:25", "quarter": 1, "down": 2,'
        ' "visible_control": {"button": "Cross", "glyph": null, "prompt": "Preplay"}}'
    )
    assert parsed is not None
    assert parsed["home_score"] == 0
    assert parsed["away_score"] == 10
    assert parsed["left_team"] == "SF"
    assert parsed["visible_control"]["button"] == "Cross"
    assert parsed["visible_control"]["prompt"] == "Preplay"


def test_football_profile_uses_gameplay_interval_on_menu(monkeypatch):
    ref = ScoreboardVlmReferee()
    ref.enabled = True
    monkeypatch.setattr(ref, "_call_vlm", lambda crop: None)
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    frame[:, :] = 12
    ref._last_call = __import__("time").time() - 7.0
    before = ref._last_call
    ref.schedule(frame, game_state="menu", game_profile="madden_27", reason="tick")
    # 7s ago is past 6s gameplay, still inside 8s menu — must schedule.
    assert ref._last_call > before


def test_vlm_cfb_menu_uses_scorebug_not_pause():
    """CFB profile + game_state='menu' must crop the scorebug (y=0.78-0.93), not center pause plate.
    
    Regression test for 2026-08-29 CFB 27 bug: when game_state was 'menu', the VLM
    cropped the center pause plate (0.12-0.52) instead of the CFB scorebug (0.78-0.93),
    causing DeepSeek to return None-None scores because it saw grass instead of the score.
    Same #108 exception pattern as Madden: known profile should use its scorebug first.
    """
    h, w = 720, 1280
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    # Pause plate region (center): red channel
    frame[int(h * 0.12) : int(h * 0.52), int(w * 0.22) : int(w * 0.78), 2] = 255
    # CFB scorebug strip (y=0.78-0.93): green channel
    frame[int(h * 0.78) : int(h * 0.93), :, 1] = 255
    
    crop = ScoreboardVlmReferee._crop(frame, game_state="menu", game_profile="cfb_27")
    assert crop is not None
    # Must contain green (CFB scorebug), not red (pause plate)
    assert int(crop[:, :, 1].max()) == 255, "CFB menu crop must include scorebug (green)"
    assert int(crop[:, :, 2].max()) == 0, "CFB menu crop must NOT include center pause plate (red)"


def test_vlm_cfb_title_overrides_madden_profile():
    """When title is 'College Football 27' but profile is madden_27, use CFB scorebug.
    
    Regression test for 2026-08-29: /health showed game_profile=madden_27 with
    game_title='EA SPORTS College Football 27'. The crop logic must check BOTH
    profile and title to detect CFB, using the CFB scorebug (y=0.78-0.93) not
    Madden HUD (y=0.93-1.00).
    """
    h, w = 720, 1280
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    # Madden HUD strip (bottom): blue channel
    frame[int(h * 0.93) :, :, 0] = 255
    # CFB scorebug strip (y=0.78-0.93): green channel
    frame[int(h * 0.78) : int(h * 0.93), :, 1] = 255
    
    crop = ScoreboardVlmReferee._crop(
        frame,
        game_state="menu",
        game_profile="madden_27",
        game_title="EA SPORTS College Football 27"
    )
    assert crop is not None
    # Must contain green (CFB scorebug), not blue (Madden HUD)
    assert int(crop[:, :, 1].max()) == 255, "CFB title must use CFB scorebug (green)"
    assert int(crop[:, :, 0].max()) == 0, "CFB title must NOT use Madden HUD (blue)"
