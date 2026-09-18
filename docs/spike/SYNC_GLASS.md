# SyncGlass v0 — frozen design (NON-CLAIM → live opt-in)

Status: **v0 shipped on `feat/sync-glass`** (live opt-in, observation plane).
Grounded in TypeSafe (state + speculative fan-out + confidence routing) and
Qoresence hard laws: never emit-under-lock, grab waits for nobody, Pattern B,
DualSense USB→laptop observe + BT→PS5 play, equalize by video-clock bind
(`syncLagMs` / `hidAt` / `lag_center_ms`) — never by deleting USB physics.

## Hard laws
1. `licenses_digits: false` forever.
2. No work on capture/HID hot path — stamp facts only; Jev on timer worker.
3. Observation plane: enqueue-only / timer, JSONL, no bus emit, no lobe locks.
4. Local deterministic fallback; `--play` alone does NOT enable.
5. v0 advisory + `/health` + glyphs only — no auto retune of capture fps / lag_center without operator GO.
6. No Truth-plane / QorTroller wrap; no haptic authorship / THROW / anti-cheat.

## Enable
`--sync-glass` / `QORESENCE_SYNC_GLASS=1`, and/or under `--jev`.

## State packet (JSON, no pixels)
```json
{
  "clock_ns": 0,
  "frame_seq": 0,
  "video": {"age_s": null, "frames": null, "pll_lock": null},
  "hid": {
    "source": "usb_play|bt|empty",
    "edges_last_n": [],
    "apm": 0.0,
    "stick_heat": 0.0,
    "hid_at_ns": null,
    "sync_lag_ms": null,
    "lag_center_ms": null
  },
  "haptic": {"co_occur_recent": false, "probe_ok": null},
  "capture": {"starve": false, "dshow_name": null},
  "ticket_glass": {"lock": null, "enabled": false}
}
```

## Fan-out (ONE request)
| ID | Type | Options / meaning |
|----|------|-------------------|
| `bind_healthy` | Noul | Pad and picture co-occur on video clock |
| `lag_class` | Choice | `ok` / `pad_ahead` / `picture_ahead` / `hid_empty_usb` / `capture_starve` / `unknown` |
| `haptic_coupled` | Noul | Vibration co-occurs with picture/outcome (observe) |
| `action` | Choice | `observe` / `recenter_soft` / `flag_operator` / `dark_overlay` |
| `severity` | Score 0–3 | Skew severity |

## Gates
Choice/Score: <0.4 observe, 0.4–0.7 soft glyphs, ≥0.7 act low-stakes.
`recenter_soft` / anything touching pacing: conf ≥0.85 — v0 still advisory only (glyph + health), code does not apply recenter.
Noul: ≥0.7 / ≤0.3 / else soft. Ambiguous → observe. Fallback dark/observe if no key.

## Glyphs
`bind` / `lag` / `haptic` — fail-closed if Jev down.

## Relation
- SyncCoroner / Qoreclock: do not duplicate clocks; SyncGlass consumes stamped lag facts.
- TicketGlass: orthogonal glass honesty; may appear as input facts only.
- Qorehaptic: co-occurrence only.

## Cadence & enable

- Tick: default `cadence_s=0.5`. Override: `QORESENCE_SYNC_GLASS_CADENCE`.
- Opt-in: `--sync-glass` / `QORESENCE_SYNC_GLASS=1`, or under `--jev` / `QORESENCE_JEV=1`.
- `--play` alone does **not** enable.
- Model: `jev-latest` (override: `QORESENCE_SYNC_GLASS_MODEL`).
- Key: `TYPESAFE_API_KEY` or `.secrets/typesafe.key` (never log the value).
- JSONL: `logs/sync_glass/sync_glass.jsonl` (override dir: `QORESENCE_SYNC_GLASS_DIR`).
- Health: `/health` → `sync_glass` (`enabled`, glyphs bind/lag/haptic, `licenses_digits: false`, `recenter_applied: false`, `capture_fps_changed: false`).

## v0 implementation

| File | Role |
|------|------|
| `qoresence/observability/sync_glass_questions.py` | Constants + five questions |
| `qoresence/observability/sync_glass.py` | Sentinel: enqueue / timer / JSONL / fallback / glyphs |
| `qoresence/core/unified_config.py` | `SyncGlassConfig` (default OFF) |
| `qoresence/cli.py` | `--sync-glass`; also under `--jev` |
| `qoresence/deck/server.py` | `/health` → `sync_glass` |
| `tests/test_sync_glass.py` | never-emits, never-locks, fallback dark/observe, default off, no hot-path blocking |

Local fallback (no SDK/key): `action=dark_overlay` or `observe`, never `recenter_soft`.
`hid_empty_usb` is honest Path B (DualSense on PS5) — observe, not a fps retune.
`capture_starve` flags the operator; still never writes `lag_center` or capture fps.

### What v0 does **not** do

- No `lag_center` recenter (`recenter_applied: false` forever in v0).
- No capture fps change (`capture_fps_changed: false` forever in v0).
- No haptic authorship (`haptic_authored: false`).
- Does not replace SyncCoroner clocks or TicketGlass honesty.
- No Truth-plane / QorTroller wrap.

### v0 ship gate

1. Constants module (`sync_glass_questions.py`).
2. Tests: never emits bus, never locks, never licenses digits, fallback dark/observe, `--play` OFF.
3. Glyphs `{bind, lag, haptic}` on `/health`.
4. Commit on `feat/sync-glass`. Do not merge unless asked.
