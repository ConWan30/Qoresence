# TicketGlass v0 — frozen design (NON-CLAIM)

Status: **v0 shipped on `feat/ticket-glass`** (live opt-in, observation plane).
Grounded in TypeSafe docs (State, Primitives, Confidence, Speculative fan-out,
Confidence-gated routing) + Qoresence observation contract (`licenses_digits: False`,
ticket-clock law, Pattern B).

Patterns used: **speculative fan-out** (one `system_one` call) + **confidence-gated
routing** (code owns consequences). Jev is text-only — state never carries pixels.

---

## Hard laws (immutable)

1. `licenses_digits: false` on every TicketGlass output forever.
2. Confirm ticket + `score_vlm_locked` remain the **only** path that may paint score digits.
3. Jev may **force dark / block paint** — it may never unlock or mint digits.
4. Observation plane: no bus emit, no lobe locks, no capture-path blocking; timer/worker.
5. Local deterministic fallback if SDK/key missing; `--play` alone does not enable.
6. No Truth-plane / QorTroller wrap in state.
7. Human HOLD beats every PASS.

---

## Cadence & enable

- Tick: every 200–300 ms situation tick (or bus enqueue + worker, same as ticket_stale).
  Default `cadence_s=0.25`. Override: `QORESENCE_TICKET_GLASS_CADENCE`.
- Opt-in: `--ticket-glass` / `QORESENCE_TICKET_GLASS=1`, or under `--jev` / `QORESENCE_JEV=1`.
- `--play` alone does **not** enable.
- Model: `jev-latest` (override: `QORESENCE_TICKET_GLASS_MODEL`).
- Key: `TYPESAFE_API_KEY` or `.secrets/typesafe.key` (never log the value).
- JSONL: `logs/ticket_glass/ticket_glass.jsonl` (override dir: `QORESENCE_TICKET_GLASS_DIR`).
- Health: `/health` → `ticket_glass` (`enabled`, glyphs, `licenses_digits: false`).

---

## State packet `TicketGlassState` (JSON object)

Text / numbers / enums only. No JPEG, no base64, no HDMI crops. Compact; last N ≤ 8.

```json
{
  "clock_ns": 0,
  "frame_seq": 0,
  "intent": {
    "play": true,
    "lens_opacity_request": 0.0,
    "mobile_connected": false,
    "x_live": false
  },
  "title": {
    "plane": "in_game|menu|pause|loading|unknown",
    "profile": "madden|cfb|cod|other|unknown",
    "locked": false
  },
  "board": {
    "score_vlm_locked": false,
    "digit_integrity_reason": "ok|ticket_stale|crop_mismatch|seq_skew|no_ticket|…",
    "confirm_age_ns": null,
    "soft_away": null,
    "soft_home": null,
    "ticket_away": null,
    "ticket_home": null,
    "crop_hash_live": null,
    "crop_hash_ticket": null,
    "ticket_stale": {
      "stale_class": "fresh|crop_moved_on|match_changed|menu_or_plate|clock_drift|unknown",
      "action": "flag_stale|watch|observe",
      "gate_reason": null,
      "freshness": null
    }
  },
  "situation": {
    "quarter": null,
    "clock": null,
    "down": null,
    "distance": null,
    "ticketed": false
  },
  "hid": {
    "source": "usb_play|bt|empty",
    "edges_last_n": [],
    "apm": 0.0,
    "stick_heat": 0.0,
    "sync_lag_ms": null
  },
  "outcome": {
    "last_events": []
  },
  "foundry": {
    "ring_fill": 0.0,
    "window_s": 0.0,
    "clip_worthy_features": {}
  }
}
```

Notes:
- Digits in `soft_*` / `ticket_*` are **already-ticketed or soft observations** for drift
  comparison — never answers Jev invents.
- `board.ticket_stale.*` is **input from the live ticket_stale pack** (do not re-ask
  stale_class in TicketGlass v0; reuse as named facts).
- Point questions at backticked paths (`board.score_vlm_locked`, `title.plane`, …).

---

## Question fan-out (ONE request)

IDs are for code only; full judgment lives in `instructions`.
Module: `qoresence/observability/ticket_glass_questions.py`.

| ID | Type | Criteria / levels | Code consequence |
|----|------|-------------------|------------------|
| `title_in_game` | Noul | true=optical title in-game; false=menu/pause/loading/unknown | Soft gate for clip/route; never alone licenses digits |
| `board_paint_block` | Noul | true=painting ticket digits would be dishonest now; false=no block signal | **Veto only**: true → force dark board paint path; false never unlocks paint |
| `moment_class` | Choice | `boring` / `build` / `clutch` / `aftermath` / `unknown` | Tags + tension; speculative |
| `clip_now` | Choice | `hold` / `cut_foundry` / `extend_window` | Foundry advisory only |
| `lens_tension` | Score | 0 Calm/invisible → 1 Mild → 2 Elevated → 3 Peak clutch | Maps to Deck/Lens opacity in code |
| `glass_route` | Choice | `dark` / `deck_only` / `lens` / `mobile` / `x_live_overlay` | Which glasses may show non-digit chrome |

### Deferred (v0.1+)

| ID | Type | Why deferred |
|----|------|--------------|
| `chat_safe` | Noul | Needs a reasoner candidate line in state; gate later, never invents score |

### Explicitly rejected

- `digits_ok` (would be misread as a license) → use `board_paint_block` only.
- Any Choice/Score that returns numeric scorelines.
- Replacing scorebug VLM or ConfirmTicket with Jev.

---

## Confidence / Noul gates (code-owned)

Align with Qoresence observation bands + TypeSafe confidence-routing (stakes scale).
Implemented in `compose_glass_verdict` (`qoresence/observability/ticket_glass.py`).

**Choice / Score** (use `.confidence`):

| Band | Rule |
|------|------|
| `confidence < 0.4` | observe / dark — do not act |
| `0.4 ≤ confidence < 0.7` | soft / watch — glyphs only, no cut |
| `confidence ≥ 0.7` | act on low-stakes (route, tension) |
| `clip_now == cut_foundry` | require `confidence ≥ 0.85` **and** `title_in_game.noul ≥ 0.7` **and** not `board_paint_block` |

**Noul** (no separate confidence — use probability):

| Signal | Act threshold |
|--------|----------------|
| `title_in_game` | ≥ 0.7 treat as in-game; ≤ 0.3 treat as not; else unknown → dark-leaning |
| `board_paint_block` | ≥ 0.7 force block; ≤ 0.3 no block signal; else soft watch |

Ambiguous → dark. Same ethos as ConfirmTicket.

`cut_foundry` fail-closed: "not `board_paint_block`" means an **explicit** no-block
(`noul ≤ 0.3`), not merely "noul is not ≥ 0.7". Watch-band paint-block kills the cut
glyph. v0 never calls Foundry export — `foundry_cut` is always `false`.

---

## Glyph card (product surface)

Three glyphs only (fail-closed if Jev down or low conf):

1. **lock** — from ticket-clock + `board_paint_block` (blocked / open / unknown)
2. **tension** — from `lens_tension` score (0–3 → opacity)
3. **cut** — from `clip_now` when high-stakes gate passes, else off

`lock == open` is observational of an already-ticketed board. It is **not** a paint
grant (`paint_unlocked` is always `false`).

MCP tool shape (later): `jev_license(state) → { tickets_advisory, glyphs, licenses_digits: false }`

---

## Relation to existing packs

| Pack | Role vs TicketGlass |
|------|---------------------|
| `ticket_stale` | Feeds `board.ticket_stale` facts; keep as dedicated sentinel |
| `jev_conductor` | Chat templates / observe lines — orthogonal; TicketGlass does not rewrite chat |
| `sync_coroner` | Sync diagnostics — do not duplicate |
| ConfirmTicket / SEQGATE | Own real blank/paint — TicketGlass advisory + veto only |

---

## v0 implementation

| File | Role |
|------|------|
| `qoresence/observability/ticket_glass_questions.py` | Constants + six questions |
| `qoresence/observability/ticket_glass.py` | Sentinel: enqueue / timer / JSONL / fallback / glyphs |
| `qoresence/core/unified_config.py` | `TicketGlassConfig` (default OFF) |
| `qoresence/cli.py` | `--ticket-glass`; also under `--jev` |
| `qoresence/deck/server.py` | `/health` → `ticket_glass` |
| `tests/test_ticket_glass.py` | never-emits, never-locks, never licenses digits, veto cannot unlock, fallback dark, default off |

Local fallback (no SDK/key): `glass_route=dark`, `clip_now=hold`, `lens_tension=0`,
`moment_class=unknown`. Paint-block noul still follows `board.ticket_stale` facts.

### What v0 does **not** do

- No Foundry cut / export / arm side effects (`foundry_cut: false` forever in v0).
- Does not replace scorebug VLM or ConfirmTicket.
- Does not enable `--x-glass` (route `x_live_overlay` is chrome-advisory only).
- Does not rewrite chat (`jev_conductor` stays orthogonal).

### v0 ship gate

1. Constants module (`ticket_glass_questions.py`).
2. Tests: never emits bus, never locks, never licenses digits, fallback dark.
3. `--play` alone OFF.
4. Qoretrust audit of `licenses_digits` + `board_paint_block` cannot unlock.
