# Join picker v0 — frozen design (NON-CLAIM)

Status: **v0 observation pack** under `--jev` / `--join-picker`.
Jev selects which already-stamped `hid_seq_line` slot belongs on the current
HDMI frame. Code owns IVC, Bind, PLL, and ghost-stick paint.

## Hard laws

1. `licenses_digits: false` forever.
2. Never invent a lag. Never interpolate a silent pad. Never write `lag_center_ms`.
3. Never re-enable play-phrase. Facts: analog + `visual_phase` + bind + Noul `hud_kind`.
4. Observation plane: timer worker; no bus emit; no lobe lock; no grab.
5. `--play` does not enable. Local heuristic if SDK/key missing.
6. DualSense USB = laptop observe. No haptic authorship.

## Enable

- `--join-picker` / `QORESENCE_JOIN_PICKER=1`
- or under `--jev` / `QORESENCE_JEV=1`
- Cadence: 0.5s
- JSONL: `logs/join_picker/join_picker.jsonl`
- Health: `/health` → `join_picker`

## Candidates (stable Choice ids)

`behind_2` / `behind_1` / `now` / `ahead_1` / `none` — neighbors of `hub_seq`.
Empty slots stay `present: false`. No interpolation.

## Compose

| Condition | Action |
|---|---|
| No present slots or `join_id=none` | dark |
| `picture_answered` ≤ 0.3 | dark |
| join conf < 0.4 | dark |
| present slot + conf ≥ 0.7 (or ≥0.4 and honesty ≥1.5) + answered ≥ 0.7 | stamp |
| else | observe |

Ghost stick still uses today’s seq in v0. `--join-picker-actuate` is a later PR.
