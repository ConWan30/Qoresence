# CIVIF — Coupled Input–Video Intelligence Framework

Observation plane only. Qoresence does **not** claim legitimacy, eligibility, or anti-cheat. DualSense often stays on the PS5; the laptop may never see HID.

## Overview

CIVIF is the **live + clip observation** layer:

- **Coupled Event Record** is the primitive (clip sidecars `civif-v0`, live ticks `civif_tick-1`).
- Highlights, coaches, search, and narrative are **queries** over those records.
- Theater LIVE (`/live.jpg`) is unchanged. Open `/civif.html` for CIVIF (JSON ~1 Hz).
- Session Theater (`/session.html`) is a separate Now + Story + Recap glass over the normalized narrative pack. Operator contract: [SESSION_THEATER.md](SESSION_THEATER.md).

## Current shipped state (Session Theater)

On `main` through recap docs **`fef4d3c`** (code **`27fc4a6`**):

`CIVIF → NarrativeEngine → normalized session view → live Session Theater → validated clip links → read-only session recap`

| Milestone | SHA | PR |
|-----------|-----|----|
| Phase 1–2 foundation | `da0fa95` | [#63](https://github.com/ConWan30/Qoresence/pull/63) |
| Live `GET /api/session/view` | `4ebdf92` | [#67](https://github.com/ConWan30/Qoresence/pull/67) |
| Event → clip linkage | `651bb5a` | [#70](https://github.com/ConWan30/Qoresence/pull/70) |
| `GET /api/session/recap` | `27fc4a6` | [#73](https://github.com/ConWan30/Qoresence/pull/73) |

Hold streamer overlay until laptop play proves a repeated broadcast use case. Overlay later is a **separate** milestone. Historical “Excluded” lists below are **as of that merge**; later rows landed in later PRs (see [SESSION_THEATER.md](SESSION_THEATER.md)).

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

## Third clock — haptic receipt (`haptic_receipt-1`)

IVC is HID-in × video. The **novel** join is HID-in × HDMI lock × haptic-out. See [HAPTIC_RECEIPT.md](HAPTIC_RECEIPT.md). Coupled only when this host has HID, the board has a ConfirmTicket, and a real `hid_output` / `imu_echo` pulse is present. PS5-bound pads stay dark. The receipt does not emit bus events and is not on Theater/MCP yet.

## Highlights and explanation
