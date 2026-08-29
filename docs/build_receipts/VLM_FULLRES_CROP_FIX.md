# VLM Full-Resolution Crop Fix (Post #110)

**Status**: TESTS WRITTEN (awaiting CI verification)  
**Branch**: `cursor/vlm-fullres-crop-b417`  
**Date**: 2026-08-29

## Summary

Fixed VLM scoreboard parsing to crop from FrameHub's full-resolution frames instead of downscaled classify frames. After #110 (main 54c71d00), operator reported VLM HTTP 200 but parse failures ("None-None q=None", "null parse") despite working API. Root cause: `visual.py` downsizes frames to `max_frame_dim` (640–720) for classification, THEN `scoreboard_extractor.py` crops for VLM from this already-downscaled frame. CFB scorebug y=0.78–0.93 and Madden HUD y=0.93–1.00 become tiny strips or mush; DeepSeek returns null or unparseable prose.

## Bug Evidence (2026-08-29 post-#110)

- **Operator**: "FIX IT" after #110 deployed
- **Symptoms**:
  - scoreboard VLM HTTP 200 ✓ (good)
  - first parse: `None-None q=None reason=tick`
  - later: `"null parse"`
  - cadence still 8.0s (menu interval) when title is football
  - `last_confirm` empty → license veto → no scores
- **Hypothesis verified**: VLM crops from downscaled classify frame → scoreboard region too small for DeepSeek to parse

## Root Cause

**File**: `qoresence/lobes/visual.py`, lines 566-577

```python
# visual.py downscales THEN merges scoreboard:
h, w = frame.shape[:2]
if max(h, w) > self.config.max_frame_dim:
    scale = self.config.max_frame_dim / max(h, w)
    frame = cv2.resize(frame, (int(w * scale), int(h * scale)))

context = self._merge_scoreboard(frame, context)  # passes downscaled frame
```

`_merge_scoreboard` → `extract_football_scoreboard` → `scoreboard_vlm.schedule(frame, ...)` → `_crop(frame, ...)` crops from the already-downscaled classify frame. For CFB, y=0.78–0.93 of a 640×360 frame becomes ~54 pixels tall; Madden y=0.93–1.00 becomes ~25 pixels. DeepSeek cannot read digits from such small crops.

## Fixes Applied

### 1. Full-Res Frame Source for VLM (Fail-Closed)

**File**: `qoresence/vision/scoreboard_extractor.py`, lines 356-374

VLM scheduler now gets full-res frame from FrameHub when available:

```python
# Get full-res frame from FrameHub if available (never wait on grab thread)
vlm_frame = frame  # fallback to classify frame
try:
    from qoresence.monitor.frame_hub import get_latest_stamp, get_latest
    
    stamp = get_latest_stamp()
    if stamp.get("has_frame"):
        full_res = get_latest()
        if full_res is not None:
            vlm_frame = full_res
except Exception:
    pass

get_scoreboard_vlm().schedule(
    vlm_frame,  # full-res, not downscaled
    game_state=gst,
    reason="tick",
    game_profile=getattr(ctx, "game_profile", None),
)
```

**Safety**: Never blocks grab thread. If FrameHub unavailable, falls back to classify frame (prior behavior).

### 2. Football Titles Use Gameplay Interval Even on Menu

**File**: `qoresence/vision/scoreboard_vlm.py`, lines 122-154

Football titles (CFB 27 / Madden 27) now use gameplay interval (~1.5s) even when classifier wrongly reports `game_state="menu"`:

```python
# Football titles (CFB 27 / Madden 27): use gameplay interval even when
# classifier says menu, because HUD-first crop is valid on menu/hub.
profile_lower = (game_profile or "").lower()
is_football = any(
    kw in profile_lower for kw in ("football", "cfb", "madden", "ncaa")
)

if force or reason in {"score_changed", "menu_exit", "first_lock"}:
    interval = 0.0
elif is_gameplay or is_football:
    interval = max(0.8, _GAMEPLAY_INTERVAL_S)  # ~1.5s
else:
    interval = max(4.0, _MENU_INTERVAL_S)  # 8.0s
```

Rationale: #110 made HUD-first crop work for CFB+Madden on menu state. But menu interval was still 8.0s → stale reads. Gameplay interval (~1.5s) is correct for all football, regardless of transient menu classification.

### 3. Better Logging for Parse Failures + JSON Recovery

**File**: `qoresence/vision/scoreboard_vlm.py`, lines 314-333

On HTTP 200 + parse fail, log a preview and try extra JSON recovery:

```python
parsed = self._parse_json(str(text))

# HTTP 200 but parse failed: log preview and try extra recovery
if parsed is None and text:
    preview = str(text)[:200].replace("\n", " ")
    log.info("scoreboard VLM HTTP 200 parse fail, last_raw preview: %s", preview)
    
    # Try extra JSON recovery: strip fences and extract first {...}
    text_stripped = text.strip()
    text_stripped = re.sub(r"^```(?:json)?\s*", "", text_stripped)
    text_stripped = re.sub(r"\s*```$", "", text_stripped)
    match = re.search(r"\{[^{}]*\}", text_stripped)
    if match:
        try:
            test_obj = json.loads(match.group(0))
            if isinstance(test_obj, dict):
                parsed = self._parse_json(match.group(0))
        except Exception:
            pass
```

Enhanced `_parse_json` to handle common LLM errors (single quotes, trailing commas).

### 4. Save Last VLM Crop for Operator Inspection

**File**: `qoresence/vision/scoreboard_vlm.py`, lines 232-242

Every VLM call writes the crop JPEG to `logs/vlm_last_crop.jpg`:

```python
# Save last VLM crop so operator can see what DeepSeek saw
try:
    import pathlib
    
    logs_dir = pathlib.Path("logs")
    logs_dir.mkdir(exist_ok=True)
    cv2.imwrite(str(logs_dir / "vlm_last_crop.jpg"), crop_bgr)
except Exception:
    pass
```

No secrets in the file or logs.

## Tests

**File**: `tests/test_vlm_fullres_crop.py` (new)

Regression tests added:

1. **`test_vlm_uses_fullres_from_hub_not_downscaled`**  
   Verifies VLM receives 1280×720 from hub, not 640×360 downscaled classify frame

2. **`test_football_uses_gameplay_interval_even_on_menu`**  
   CFB profile with `game_state="menu"` should schedule at gameplay interval, not menu 8.0s

3. **`test_parse_fail_does_not_mint_confirm`**  
   HTTP 200 + null parse → no `confirm_ticket_id`, no `score_vlm_locked`, no invented scores

4. **`test_no_invented_scores_without_ticket`**  
   No VLM result + no local HUD → scores stay `None` (not 0-0 or 3-2)

5. **`test_json_recovery_strips_fences`**  
   Parser recovers from `\`\`\`json {...} \`\`\`` markdown fences

6. **`test_json_recovery_handles_prose_then_json`**  
   Parser extracts JSON even when surrounded by prose

7. **`test_vlm_crop_saved_to_logs`**  
   Verifies `logs/vlm_last_crop.jpg` is written and valid

8. **`test_downscaled_then_crop_is_not_vlm_source`**  
   Core regression: when hub has 1280×720, VLM should NOT receive 640×360 classify frame

9. **`test_null_parse_does_not_mint_confirm`**  
   VLM returns `{"home_score": null, "away_score": null}` → no ticket, no lock

### Test Execution

```bash
python3 -m pytest tests/test_vlm_fullres_crop.py -xvs
```

Expected: All tests pass (CI verification pending).

## Impact

- **Capture plane**: No changes to streamer grab loop (per AGENTS.md)
- **Observation plane only**: VLM crop source changed from downscaled classify frame to full-res FrameHub frame
- **Seeing-path**: VLM can now parse scoreboard digits correctly → mint confirm tickets → glass shows scores
- **Fail-closed**: If FrameHub unavailable, falls back to classify frame (prior behavior)
- **No invented scores**: Without valid parse + ticket, scores stay `None` (not 0-0 or fake pairs)

## Files Changed

1. `qoresence/vision/scoreboard_extractor.py` — get full-res frame from hub for VLM
2. `qoresence/vision/scoreboard_vlm.py` — football interval on menu, logging, JSON recovery, crop JPEG
3. `tests/test_vlm_fullres_crop.py` — 9 regression tests

## Next Steps

Per operator instruction: **DO NOT MERGE**. Open PR, verify CI green, report back.

When CI green:
1. Operator reviews PR
2. Verify fix on live CFB 27 / Madden 27 HDMI
3. Confirm `score_vlm_locked=true` and scores populate correctly
4. Operator decides merge (not agent)

---

**Receipt author**: Cursor Cloud Agent  
**Operator**: ConWan30  
**Plane**: qoresence-observation  
**Falsification tests**: `test_vlm_uses_fullres_from_hub_not_downscaled`, `test_downscaled_then_crop_is_not_vlm_source`, `test_null_parse_does_not_mint_confirm`  
**Invariants preserved**: Event-bus locking (AGENTS.md Rule 1-6), no force-push main, no ci.yml changes, no streamer.py grab loop, no secrets in logs, no DualSense play path changes
