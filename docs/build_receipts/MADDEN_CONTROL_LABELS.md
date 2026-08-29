# Receipt — Madden 27 control labels (feat/madden-control-labels)

**Date:** 2026-08-29  
**Plane:** qoresence-observation  
**Dest denied:** qortroller-truth  

## What landed

- `ControlObservation.to_dict()` carries `plane`.
- `get_madden_lookup()` caches the JSON legend off the grab loop.
- Dead HID-mask comments removed from `observe_button_press`.
- `observation_wire` injects situation `game_state` / `game_profile` into the picture dict before lookup so a real `visual_phase` can select a sheet.
- MCP `get_observation` includes `control` from `build_observation_wire`. Licensed speech is `pad label {button} = {verb} (sheet {mode})`. Unlabeled stays silent.

## Claim ceiling

A verb is an EA sheet label. It is not a snap, catch, score, possession, or eligibility fact.

## Residuals (HOLD)

- JSON `defense_pursuit` still lacks EA 27 four-way tackle stick Left=Lunge / Right=Wrap. No silent rewrite.
- `visual_phase` emitter quality is unchanged. Missing phase → unlabeled.
- Combo chords (L2+R2+Cross) are not resolved.
- DualSense-on-PS5 still needs USB or Remote Play to appear in `hid_by_seq`.

## Tests

- `tests/test_madden_controls_observation.py` (phase map, plane, grab isolation)
- `tests/test_mcp.py` (`control` pack is legend-only)

## Files

- qoresence/observation/madden_controls.py
- qoresence/deck/observation_wire.py
- qoresence/mcp/observation.py
- qoresence/mcp/server.py
- tests/test_madden_controls_observation.py
- tests/test_mcp.py
- docs/build_receipts/MADDEN_CONTROL_LABELS.md

## Local green

head=3ce65fea692389b4e1d4f14c0fdd0243e8eaa4fa
