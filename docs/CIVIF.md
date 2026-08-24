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
- **Coach panel** — Timing, Pattern, and Situation reports from `GET /api/civif/live` (`coaching_reports`, plus legacy `coaching_report` for Timing).

## Coaching

A session can have **more than one coach**. TimingCoach and PatternCoach each emit a `CoachingReport` with the same envelope. Future coaches (situation, narrative) should reuse that shape.

All coaches are **read-only observation**. They do not claim anti-cheat, eligibility, or legitimacy. They only fill `metrics` and `issues` when DualSense is bodied **on this host** and the scoreboard is locked. Reports are built after HDMI clip sidecar write and on pilot closeout (in memory). JSON under `logs/civif/` only if `QORESENCE_CIVIF_COACH_LOG=1`. MCP `civif_coaching_report` is **not** in `tools/list` yet.

### CoachingReport contract

Dataclass `qoresence.core.civif_tick.CoachingReport` (`schema_version: coach-1`), also re-exported from `qoresence.core.types`.

| field | meaning |
|-------|---------|
| `session_id` | SessionAuthority id |
| `schema_version` | `coach-1` |
| `coach_type` | `timing` or `pattern` (future types keep this string) |
| `metrics` | Coach-specific numbers. **Must be `{}` when unbodied or unlocked.** |
| `issues` | `{type, description, clip_ids}`. **Must be `[]` when unbodied or unlocked.** |
| `controller_bodied` | Pad/IMU on this host |
| `board_locked` | Trusted scoreboard digits |
| `generated_at_ns` | Monotonic clock when the report was built |

Hard invariant: if `controller_bodied == false` or `board_locked == false`, coaches must not invent latencies, button names in issues, or score digits. Empty `metrics`/`issues` is the only honest payload.

### TimingCoach

`qoresence.foundry.timing_coach` (facade `qoresence.agents.timing_coach`).

Pairs a bodied key-press with the **next locked scoreboard digit change**. Latency is stored in **nanoseconds**.

Typical `metrics`:

- `latency_samples`
- `median_latency_ns` (operator UI converts to ms)
- `p75_latency_ns` / `p90_latency_ns`
- `late_input_rate` (fraction 0–1, not a percentage in JSON)
- `late_threshold_ns` (400 ms)

`issues`: `type: late_input` only with ≥5 samples and ≥40% of latencies above 400 ms. Description is observational. `clip_ids` are the highest-latency evidence clips.

### PatternCoach

`qoresence.foundry.pattern_coach` (facade `qoresence.agents.pattern_coach`). Same fail-closed gate.

- Same-button spam: more than 8 presses in a 2 s window.
- Stick→R2 gap outside 40–350 ms.

Typical `metrics`: `spam_windows_count`, `mistimed_combo_count`, `spam_rate` (windows per minute of the observed span).

`issues`: `button_spam` (≥3 windows) and/or `mistimed_combo` (≥5 pairs), each with observational text and `clip_ids`. Pattern reports may also be written as `logs/civif/coaching_<session>_pattern.json` when the log env is on.

### SituationCoach

`qoresence.foundry.situation_coach`. Compares press-to-score latency and spam windows across **stamped** locked situation fields only.

- Red zone vs not: `yard_line <= 20`. If `yard_line` is null, those metrics/issues are omitted (not invented).
- Clutch vs not: stored `clutch_score >= 0.6`.
- Issues (`red_zone_latency`, `red_zone_spam`, `clutch_latency`, `clutch_spam`) only when median latency differs by more than 100 ms or spam-rate by more than 0.1.

### Session summary JSONL

When `QORESENCE_CIVIF_SUMMARY_LOG=1`, after coaches run, append one line to `logs/civif/session_summary.jsonl` if at least one `CoachingReport` exists (`qoresence.foundry.civif_summary`). Coach-specific keys are omitted when that coach is absent. No UI.

### Operator view (Coach panel)

`/civif.html` polls `GET /api/civif/live` ~1 Hz (JSON, not JPEG). The Coach panel shows the selected `coach_type` from `coaching_reports`.

- No matching report → “insights unavailable (no report yet).”
- Report present but unbodied or unlocked → “insights unavailable (controller not bodied or board unlocked).”
- Otherwise: compact metrics plus up to 3 issues and `/media/clips/<id>.mp4` evidence links.

### EventRecord and NarrativeEngine

`event-1` dataclass `EventRecord` (`qoresence.core.civif_tick`, re-exported from `types.py`): `event_id`, `event_type` (`press_to_score`, `spam_window`, `situation_shift`), clocks, optional `input_summary` / `situation_summary` / `evidence`.

`NarrativeEngine` (`qoresence.foundry.narrative_engine`) builds a session `narrative.json` (`schema_version: narrative-1`) from live ticks after coaches. Button names only when bodied; score/yard fields only when locked. Write `logs/civif/narrative_<session>.json` when `QORESENCE_CIVIF_NARRATIVE_LOG=1`. Not an MCP tool (`civif_narrative` remains reserved). Clip `narrate_clip` is unchanged.

Session Theater (`/session.html`) is a Now + Story view of that pack. Live sessions come from read-only `GET /api/session/view`; allowlisted fixtures remain available as `?fixture=…`. It does not change `/civif.html`, HDMI Theater, or MCP. Score/yard digits render only through `LockedValue` after `session_view.normalize_pack`.

### Milestone: Phase 1–2 Session Theater foundation

Recorded on `main` as **`da0fa95`** ([#63](https://github.com/ConWan30/Qoresence/pull/63)). Acceptance: fail-closed normalization boundary, UI renders only the normalized view, Gamer/Analyst share that view, empty persisted vs not-persisted are distinct, fixtures are allowlisted, malformed packs do not 500.

Included:

- Fail-closed session-pack normalization (`session_view.normalize_pack`).
- Locked-only score and yard rendering (`LockedValue`).
- Bodied-only HID identity exposure.
- Now HUD and Story views.
- Gamer and Analyst presentation modes.
- Explicit persisted versus non-persisted empty states.
- Malformed-pack handling without route-level 500 errors.
- Allowlisted fixture access.
- 62 targeted and related tests passing locally (Session Theater, narrative, CIVIF, MCP, deadlock, OTel).

Excluded (later work at the time of merge):

- Live `GET /api/session/view` (Phase 3, [#64](https://github.com/ConWan30/Qoresence/issues/64)).
- Recap API.
- Clip dock.
- Glass SPA / HDMI Theater.
- `/civif.html` changes.
- MCP `tools/list` changes.

### Milestone: Phase 3 live session-view API

Recorded on `main` as **`4ebdf92`** ([#67](https://github.com/ConWan30/Qoresence/pull/67), closes [#64](https://github.com/ConWan30/Qoresence/issues/64)). Acceptance: read-only `GET /api/session/view` returns only a `normalize_pack` envelope; `stale` is a freshness flag, not a `status`; `/session.html` polls that route only; empty, not-persisted, unavailable, invalid, and stale-age cases stay distinct.

Included:

- Live read-only `GET /api/session/view`. Live generate uses `persist=False` (no NarrativeEngine persist-path change).
- Envelope fields: `ok`, `status`, `session`, `view`, `freshness` (`generated_at`, `last_event_at`, `age_ms`, `stale`).
- `view` always `session-view-1` from `normalize_pack` (never a raw `narrative-1` pack).
- Content `status`: `live`, `empty`, `not_persisted`, `unavailable`, `invalid`.
- `ok: false` only for `invalid`.
- `stale` is a freshness-only flag — aged content stays `status: "live"` with `freshness.stale: true`.
- Fail-closed unavailable and malformed: missing session/fixture → `unavailable`; rejected source → `invalid` with a normalized empty `view` (HTTP 200, no route 500).
- If a later live load is unavailable, return the last valid `live` / `empty` / `not_persisted` envelope and set `freshness.stale: true`.
- `/session.html` ~1 Hz poll of the API; no client fetch of `/session_fixtures/*.json`.
- Allowlisted fixture query (`?fixture=`) still served through the same envelope.
- Locked-only score/yard and bodied-only HID, unchanged from Phase 1–2.
- 43 passing Phase 3, narrative, and MCP tests, plus live Chromium smoke of `/session.html`.

Excluded (unchanged; not in #67):

- Recap API.
- Clip dock.
- Glass SPA / HDMI Theater.
- `/civif.html` changes.
- MCP `tools/list` changes (`civif_session_view` is not listed).
- NarrativeEngine behavior or persist path (live generate uses `persist=False`).
- CI full-matrix fail-fast ([#65](https://github.com/ConWan30/Qoresence/issues/65)); first full-suite stop remains `tests/test_civif_index.py`.

Project state: Phase 1–2 on `main` (`da0fa95`, docs `#66` / `85e104a`). Phase 3 live-session path on `main` (`4ebdf92`):

`CIVIF session → NarrativeEngine → normalized session view → read-only live API → stale-aware Session Theater`.

Next work is stabilization (exercise the six envelope cases, watch CIVIF/MCP, leave [#65](https://github.com/ConWan30/Qoresence/issues/65) independent). Do not start clip linkage, recap, or streamer presentation until that choice is explicit.

## Future (reserved)

Dataclasses `CoachingReport` (`coach-1`) and `EventRecord` (`event-1`) in `qoresence/core/civif_tick.py`. MCP names **not** listed yet: `civif_coaching_report` (bodied), `civif_narrative` (board locked). Use `coach_clip` / `narrate_clip` today. New coaches should add a `coach_type` and the same fail-closed empty `metrics`/`issues`.
