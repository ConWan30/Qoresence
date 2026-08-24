# CIVIF — Coupled Input–Video Intelligence Framework

Observation plane only. Qoresence does **not** claim legitimacy, eligibility, or anti-cheat. DualSense often stays on the PS5; the laptop may never see HID.

## Overview

CIVIF is the **live + clip observation** layer:

- **Coupled Event Record** is the primitive (clip sidecars `civif-v0`, live ticks `civif_tick-1`).
- Highlights, coaches, search, and narrative are **queries** over those records.
- Theater LIVE (`/live.jpg`) is unchanged. Open `/civif.html` for CIVIF (JSON ~1 Hz).

## CIVIF invariants

These are fail-closed observation guarantees. They are locked in by
`tests/test_civif_invariants.py` (and `tests/test_civif_bodied.py`).

- If the pad is on the PS5 (controller not bodied on this host), `input_ticks` is empty and no button names are shown in highlights, coaches, or any CIVIF JSON (`/civif.html` polls that JSON ~1 Hz). Timing and pattern coaches are withheld (`null`).
- Score digits (home/away, down, distance, and similar) are only included when the scoreboard is locked (`board_locked == true`). When unlocked, situation digit fields are `null` / omitted. Highlights do not invent scores or outcome tags.
- Highlights include an `explanation` that mirrors the **real** ranking terms: coupling score, `board_locked`, `controller_bodied`, `key_inputs` only if bodied, `outcome_tag` only from a locked board’s stored `clutch_kind` or an existing chapter label. No synthetic touchdowns or invented digits.
- Ranking may still use coupling and a locked board when the pad is unbodied; it must not use detailed HID patterns from an unbodied host.
- CIVIF is an **observation plane only**. It does not make anti-cheat, eligibility, or legitimacy claims.

Internal, non-UI counters (`qoresence.foundry.civif_metrics`) may tally locked-tick rate, whether the pad was ever bodied, and highlight coupling min/max/mean. They do not emit bus events.

## Live Coupled Tick Schema (`civif_tick-1`)

Fields on each live tick (`GET /api/civif/live` → `record`):

| field | meaning |
|-------|---------|
| `session_id` | SessionAuthority id |
| `clock_ns` / `frame_seq` | video clock from IVC |
| `input_ticks` | HID edges since last tick (`button`, `edge_type`, `clock_ns`) |
| `situation_snapshot` | locked board fields or `null` |
| `board_locked` | OCR/VLM scoreboard lock |
| `controller_bodied` | pad/IMU on **this host** |
| `ivc_version` | `ivc-v0` |
| `schema_version` | `civif_tick-1` |

Nested `input` / `situation` / `coupling` keep the clip-era `civif-v0` shape so older readers still work.

**Invariants**

- Situation digits only when `board_locked` is true.
- `input_ticks` is empty when `controller_bodied` is false (valid: pad on the console).
- Breaking field changes bump `schema_version` (e.g. `civif_tick-2`). Clip files stay `civif-v0` until a sidecar bump.

IVC enqueues ticks **after** dropping its lobe lock. The CER worker only appends JSONL; it does not emit bus events.

## Highlights and explanation

`civif_highlights` / `/api/civif/highlights` return `HighlightRecord`s. `explanation` mirrors ranking:

- `coupling_score`
- `board_locked` / `controller_bodied` / `situation_present`
- `key_inputs` only if bodied
- `outcome_tag` only from locked situation `clutch_kind` or an existing chapter label — never invented

Read-only. MCP never writes clips.

## Coupled query spec

`civif_query_clips` / `/api/civif/query`:

- `session_id` (optional)
- `min_coupling_score`
- `board_locked_only`
- `controller_bodied_only`
- `situation_filters.clutch_score_min` only if a clutch number is **stored** (not invented). Yard-line / red-zone is not filtered until those fields are stamped.

`/civif.html` checkboxes map to those filters.

## Bodied controller invariant

`controller_bodied` is true when this host has InputRing edges in the tick window **or** IVC `imu_bodied`. If DualSense stays on the PS5, the flag is false.

Gated when unbodied:

- Live `input_ticks` and coach timing/pattern
- Highlight `key_inputs`

Highlights may still rank on coupling score and locked board without pad analytics.

## Operator usage (`/civif.html`)

- **board_locked yes/no** — trust score digits only when yes.
- **controller_bodied yes/no** — trust pad timing only when yes (PAD WAIT on Theater is the same honesty).
- HDMI stays on Theater; this page does not poll JPEG.

## CoachingReport (TimingCoach)

Internal `coach-1` reports (`qoresence.foundry.timing_coach`, facade `qoresence.agents.timing_coach`). **Not** in MCP `tools/list` yet (`civif_coaching_report` remains reserved).

- Generated after HDMI clip sidecar write and on pilot closeout (in memory; optional `logs/civif/coaching_<session>.json`).
- Detailed `metrics` / `issues` only when **both** `controller_bodied` and `board_locked` are true. Otherwise `metrics` is `{}` and `issues` is `[]`.
- `metrics`: `latency_samples`, `median_latency_ns`, `p75`/`p90`, `late_input_rate` (fraction of press→next locked scoreboard-digit-change latencies above 400 ms).
- `issues`: `late_input` with evidence `clip_ids` when there are at least 5 samples and ≥40% are late. Descriptions stay observational (no invented play results).
- Observation plane only. Not anti-cheat.
- `/civif.html` **Coach (Timing)** panel reads `coaching_report` from `GET /api/civif/live` (~1 Hz JSON).

## CoachingReport (PatternCoach)

Internal `coach-1` with `coach_type: "pattern"` (`qoresence.foundry.pattern_coach`). Not in MCP `tools/list`. Same fail-closed gate as TimingCoach. Detects repeated same-button spam windows and stick→R2 gaps outside a simple band. Reports are stored in memory (and `logs/civif/coaching_<session>_pattern.json` when `QORESENCE_CIVIF_COACH_LOG=1`). `/civif.html` still shows TimingCoach only.

## Future (reserved)

Dataclasses `CoachingReport` (`coach-1`) and `EventRecord` (`event-1`) in `qoresence/core/civif_tick.py`. MCP names **not** listed yet: `civif_coaching_report` (bodied), `civif_narrative` (board locked). Use `coach_clip` / `narrate_clip` today.
