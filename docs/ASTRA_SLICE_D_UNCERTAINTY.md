# Astra Slice D — Measurable uncertainty channels

**Status:** implemented. Default OFF via `QORESENCE_OBSERVATIONS` (unchanged).

## Goal

Stop collapsing trust into one confidence percentage. Each observation record
carries `uncertainty_channels` with six independent dimensions:

| Channel | Measures |
|---------|----------|
| `capture_freshness` | HDMI frame age (`video.age_s`) |
| `ocr_visual_read` | Detector/VLM read confidence when frozen |
| `input_availability` | DualSense on PS5 vs joined HID on this host |
| `clock_alignment` | Tick vs coupling `seq_skew` when known |
| `moment_boundary` | Inferred / closed / timeout boundary state |
| `outcome_confirmation` | Scoreboard qualification vs unassigned outcome |

Empty channel dict `{}` means **abstain** — empty beats a lie.

## Behavior

- Channels are refreshed on every reducer revision from **frozen** evidence
  `channel_inputs` (journaled for replay).
- Live worker attaches best-effort `collect_live_signals()` before reduction.
- Scoreboard confirmation (`state=confirmed`) sets `outcome_confirmation` only;
  `input_availability` stays `not_on_this_host` until HID is separately observed.
- No top-level `confidence` field on records.

## Surfaces

- `GET /api/observations` schema `qoresence-observations-2`
- AgentGlass `snapshot().observations` (same payload)
- `observations.html` renders per-channel rows

## Tests

```powershell
python -m pytest tests/test_observation_uncertainty.py tests/test_observation_lifecycle.py -q
```

Draft only until operator GO MERGE.
