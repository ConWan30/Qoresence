# CFB 27 VLM Menu Crop Fix

**Status**: PENDING CI  
**Branch**: `cursor/cfb-vlm-menu-crop-4ca4`  
**Date**: 2026-08-29

## Summary

Fixed scoreboard VLM crop logic and profile publishing to handle CFB 27 when `game_state` is misclassified as `'menu'` while the title is "EA SPORTS College Football 27". Extended the #108 Madden HUD-first pattern to CFB: detect CFB from both title AND profile, use CFB scorebug (y=0.78-0.93) first even on menu, and ensure situation publishes `cfb_27` profile not `madden_27`.

Added INFO-level logging for all VLM outcomes (skip/HTTP/null/success) so silent failures are visible, plus an inflight watchdog to clear stale `_inflight` if a VLM thread hangs beyond the HTTP timeout.

## Bug Evidence (2026-08-29 live HDMI, SHA 665227d, ~2h play)

- **LIVE `/health`**: `game_profile=madden_27`, `game_title="EA SPORTS College Football 27"`, `game_state=menu`, `score_vlm_locked=false`, `last_confirm` empty, license veto
- **play-live-665227.err**: VisualRuntime DeepSeek started; **ZERO** lines matching "scoreboard VLM" success OR "scoreboard VLM HTTP" warnings
- **Quicksilver chat timeouts** are the talk path, not this
- **Issue #108** already gave Madden HUD-first for `is_madden_profile` only
- **situation.game_state** stuck at "menu", scores all null, `title_hysteresis=overlay-rejected`

## Hypothesis (verified by fix)

1. **Profile mismatch**: Published profile stays `madden_27` while title is CFB 27, so Madden bottom-bar crop (y=0.93-1.00) hits the CFB ticker; prompt then nulls ticker. `_merge_scoreboard` in visual.py already maps college/ncaa/cfb title → cfb_27 — but situation model didn't re-map when it ingested the context.

2. **Menu state → wrong crop**: `game_state=menu` caused CFB path to use pause-plate crop (center field, y=0.12-0.52) not CFB scorebug (y=0.78-0.93).

3. **Silent failures**: VLM failures were `log.debug` or silent, so a hung or never-scheduled referee looked like a healthy session. `extract_football_scoreboard` only offers a worker; if scoreboard-lock is dead or `_inflight` sticks, the board stays empty.

## Fix (smallest fail-closed)

### A) Crop from TITLE + profile (CFB exception like #108 Madden)

**File**: `qoresence/vision/scoreboard_vlm.py`

- Added `game_title` parameter to `schedule()` and `_crop()` methods
- Added `_is_cfb_context(game_profile, game_title)` helper: detects CFB/college/NCAA from either field
- Updated `_crop()` logic: if `is_madden or is_cfb`, use scorebug first even on menu (HUD-first / scorebug-first pattern from #108), pause crop becomes fallback
- Never stitch ticker — that used to feed Gemini other-games crawl

**Updated caller**: `qoresence/vision/scoreboard_extractor.py` line 365 now passes `game_title=getattr(ctx, "game_title", None)` to `schedule()`

### B) Publish correct game_profile (cfb_27 not madden_27)

**File**: `qoresence/agents/situation_model.py`

- Added title → profile re-mapping in `_handle_visual_context()` (same logic as visual.py `_merge_scoreboard`)
- When title contains "college"/"ncaa"/"cfb" → force `ctx.game_profile = "cfb_27"`
- When title or profile contains "madden" → `"madden_27"`
- This ensures the published situation always has the correct canonical profile

### C) INFO-log all scoreboard VLM outcomes

**File**: `qoresence/vision/scoreboard_vlm.py`

- `schedule()` now logs skip reasons at INFO: `"scoreboard VLM skip: inflight"` or `"skip: interval (%.1fs < %.1fs)"`
- `_run()` thread logs: success at INFO (already existed), **null parse** at INFO, **failures** at INFO (was debug)
- `_call_vlm()` logs HTTP status at INFO: `"scoreboard VLM HTTP 200"` or `"HTTP 402"` etc.
- **No secrets logged** — only status codes, skip reasons, parsed scores

### D) Inflight watchdog

**File**: `qoresence/vision/scoreboard_vlm.py`

- Added `_inflight_since` timestamp field to track when `_inflight` was set
- In `schedule()`, before checking `if self._inflight`, check if `(now - self._inflight_since) > 16.0` (HTTP timeout 14s + 2s buffer)
- If stale, log `"scoreboard VLM watchdog: clearing stale inflight (%.1fs)"` and clear `_inflight`
- This allows the next tick to run if a VLM thread hangs or `_inflight` sticks

## Tests

**Files**: `tests/test_scorebug_crops.py`, `tests/test_scoreboard_vlm.py`

### New tests added:

1. **`test_vlm_cfb_menu_uses_scorebug_not_pause()`** — CFB profile + menu → scorebug (green y=0.78-0.93), not pause plate (red y=0.12-0.52)

2. **`test_vlm_cfb_title_overrides_madden_profile()`** — title="EA SPORTS College Football 27" + profile="madden_27" → CFB scorebug (green y=0.78-0.93), not Madden HUD (blue y=0.93-1.00)

3. **`test_vlm_watchdog_clears_stale_inflight()`** — Manually set `_inflight=True` + `_inflight_since=20s ago`, call `schedule(force=True)` → watchdog clears stale, new call proceeds

4. **`test_situation_model_maps_cfb_title_to_cfb_profile()`** — visual_context with `game_profile=madden_27` + `game_title="EA SPORTS College Football 27"` → situation state has `game_profile="cfb_27"`

## Crop Fractions

- **CFB scorebug** (primary): `(0.12, 0.88, 0.78, 0.93)` — red/blue bar, ticker excluded (y > 0.93)
- **Madden HUD** (reference): `(0.00, 1.00, 0.93, 1.00)` — full-width bottom strip
- **Pause plate** (fallback): `(0.22, 0.78, 0.12, 0.52)` — center field

## Impact

- **Capture plane**: No change to streamer grab loop (per AGENTS.md)
- **Observation plane**: VLM crop + situation profile mapping — fail-closed to CFB-first when title or profile is CFB
- **Seeing-path**: When game_state is wrongly 'menu' during live CFB 27, VLM now sees the CFB scorebug (not pause plate or Madden HUD) → can parse + mint confirm ticket
- **Logs**: VLM failures now visible at INFO (not silent debug)

## Next Steps

PR is **DRAFT** per operator instruction (`plane=qoresence-observation`, do not merge, do not touch capture/streamer/grab thread).

When CI passes:
1. Verify fix resolves `/health` showing correct `game_profile=cfb_27` (not `madden_27`) when title is CFB 27
2. Verify `scoreboard VLM` logs appear at INFO during live play (skip/HTTP/success/null)
3. Verify `score_vlm_locked=true` and `confirm_ticket_id` populated during CFB 27 gameplay with menu misclassification

---

**Receipt author**: Cursor Cloud Agent  
**Operator**: ConWan30  
**Plane**: qoresence-observation  
**Falsification tests**: `test_vlm_cfb_menu_uses_scorebug_not_pause`, `test_vlm_cfb_title_overrides_madden_profile`, `test_vlm_watchdog_clears_stale_inflight`, `test_situation_model_maps_cfb_title_to_cfb_profile`  
**Invariants preserved**: Event-bus locking (AGENTS.md Rule 1-6), no force-push main, no ci.yml rewrite, no streamer.py grab loop changes, no secrets logged, no remount Theater rail cards, no USB path=play flip
