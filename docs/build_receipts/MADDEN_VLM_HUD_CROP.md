# Madden VLM HUD Crop Fix (PR #108)

**Status**: GREEN (tests/test_scorebug_crops.py all 7 tests pass)  
**Branch**: `cursor/madden-vlm-hud-crop-fix-4a0b`  
**Head SHA**: 4ac2ae2  
**Date**: 2026-08-29

## Summary

Fixed scoreboard VLM crop logic to prioritize Madden bottom HUD (y=0.93–1.00) even when `game_state` is misclassified as `'menu'`. The previous logic used the CFB center pause-plate crop (y=0.12–0.52) when game_state was menu/lobby/hub/paused, causing DeepSeek to see center field grass instead of the scorebug and return `None-None` scores.

## Bug Evidence (2026-08-29 live HDMI)

- **Operator**: ConWan30 sit-down at main 3942926
- **LIVE `/health`**: `game_profile=madden_27`, `game_state=menu`, `score_vlm_locked=false`, `confirm_ticket_id` empty
- **play-live.err**: one VLM result `scoreboard VLM → None-None q=None (paused=False reason=tick)` at 00:42
- **Attached frame** (`eye-check-bounce.png`): live Madden 27 gameplay with white bottom HUD showing `NO 17, MIA 20, 4th 0:44, 1ST & 10`
- **Scorebug location**: y≈0.93–1.00 (bottom strip)
- **VLM was cropping**: y≈0.12–0.52 (center pause plate) — missed the HUD entirely

## Root Cause

In `ScoreboardVlmReferee._crop()` (lines 203-209), when `game_state` was in `{"menu", "lobby", "hub", "paused", "pause"}`, the code used `_PAUSE_FRAC` (center 0.22–0.78 x, 0.12–0.52 y) as the primary crop, regardless of game profile.

For Madden, the scorebug is always in the bottom HUD strip (y=0.93–1.00), not the center pause plate. When `game_state` was misclassified as `'menu'` during live gameplay, the VLM never saw the scorebug.

## Fix

**File**: `qoresence/vision/scoreboard_vlm.py`

### Changes

1. **Import `is_madden_profile`** (line 25):
   ```python
   from qoresence.vision.scorebug_crops import CFB_PRIMARY_SCOREBUG, is_madden_profile, primary_scorebug_crop
   ```

2. **Updated `_crop()` method** (lines 202-216):
   - For Madden profiles (`is_madden_profile(game_profile)`), **always** try HUD crop first, regardless of `game_state`
   - Pause crop becomes fallback only
   - Non-Madden profiles preserve original behavior: menu → pause first

**Crop Fractions**:
- **Madden HUD** (primary): `(0.00, 1.00, 0.93, 1.00)` — full-width bottom strip
- **Pause plate** (fallback): `(0.22, 0.78, 0.12, 0.52)` — center plate

## Test

**File**: `tests/test_scorebug_crops.py`

Added regression test `test_vlm_madden_menu_still_uses_hud_crop()` that verifies:
- Frame with center pause plate (red channel at y=0.12–0.52)
- Frame with Madden HUD strip (blue channel at y=0.93–1.00)
- Call `_crop(frame, game_state="menu", game_profile="madden_27")`
- **Assert**: crop contains blue (HUD), not red (pause plate)

### Test Results

```bash
$ python3 -m pytest tests/test_scorebug_crops.py -xvs
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.4, pluggy-1.6.0
rootdir: /workspace
configfile: pyproject.toml
collected 7 items

tests/test_scorebug_crops.py::test_cfb_bands_unchanged PASSED
tests/test_scorebug_crops.py::test_unknown_and_ncaa_use_cfb PASSED
tests/test_scorebug_crops.py::test_madden_uses_evidence_bands PASSED
tests/test_scorebug_crops.py::test_madden_primary_is_full_width_bottom_strip PASSED
tests/test_scorebug_crops.py::test_vlm_default_crop_still_excludes_ticker PASSED
tests/test_scorebug_crops.py::test_vlm_madden_crop_takes_bottom_strip PASSED
tests/test_scorebug_crops.py::test_vlm_madden_menu_still_uses_hud_crop PASSED

============================== 7 passed in 0.70s ===============================
```

## Impact

- **Capture plane**: No change to streamer grab loop (per AGENTS.md)
- **Observation plane**: VLM crop logic only — fail-closed to HUD-first for Madden
- **Seeing-path**: When game_state is wrongly 'menu' during live Madden, VLM now sees the scorebug → can mint confirm ticket

## Next Steps

PR #108 is **DRAFT** per operator instruction. Do NOT merge. Operator ConWan30 typed GO (not GO MERGE).

When ready:
1. Verify fix on live Madden 27 HDMI
2. Confirm `score_vlm_locked=true` and `confirm_ticket_id` populated during gameplay
3. Mark PR ready (if operator approves)

---

**Receipt author**: Cursor Cloud Agent  
**Operator**: ConWan30  
**Plane**: qoresence-observation  
**Falsification test**: `test_vlm_madden_menu_still_uses_hud_crop`  
**Invariants preserved**: Event-bus locking (AGENTS.md Rule 1-6), no force-push main, no ci.yml rewrite, no streamer.py grab loop changes, no possession invention (#104 HOLD)
