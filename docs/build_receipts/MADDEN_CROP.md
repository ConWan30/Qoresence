# Madden HUD crop — pointer

Local receipts (not in git; `logs/` is ignored):

- `logs/build/madden_crop_discovery_20260816_082435.json`
- `logs/build/madden_crop_analysis_20260816_082435.json`
- `logs/build/madden_crop_20260816_082435.json`

Code: `qoresence/vision/scorebug_crops.py`

CFB bands unchanged. Madden uses the white bottom strip measured on preexisting 2026-08-14/15 frames (`y≈0.9375–1.00`). Unknown profile falls back to CFB.

**Operator HOLD:** human alone commits.
