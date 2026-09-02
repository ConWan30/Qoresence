# Look-license graphs

Observation-plane only. Qoresence is a **Gaming Streaming Observatory Engine**: one capture aperture, one clock, many read-only glasses. These graphs license the **next look** — which crop, frame, ticket, or unit may run. They do not play, narrate, or self-improve.

> DriveGraph remembers what happened. The unit graph decides what may run. The learning edge makes the next DriveGraph cut work from accepted evidence. Look-license graphs decide which look is allowed next.

Flag: `--look-graphs` / `QORESENCE_LOOK_GRAPHS`. Default **OFF**. `--play` does not enable this. When OFF, behavior matches current main: no license read, no license write.

Per-graph dark-ship: `QORESENCE_LOOK_TICKET_DAG`, `QORESENCE_LOOK_CROP`, `QORESENCE_LOOK_SAME_SEQ`, `QORESENCE_LOOK_REFUSE`, `QORESENCE_LOOK_SCALE`, `QORESENCE_LOOK_NEGATIVE` (set `0`/`false`/`off` to disable one graph while the master flag is on).

## Layers

| Layer | Type | Role |
|---|---|---|
| **A — DriveGraph** | attributed temporal causal DAG | What happened this drive. Unchanged. Cap 48 / floor 8 / ceiling 96. |
| **B — Unit graph** | directed control-flow with gates | What may run. |
| **C — Learning edge** | append-only constraint store | What the next splitter may read. |
| **D — LookLicense** | next-look receipt | Which crop / frame / mint / skip is licensed now (`qoresence/graphs/`). |

A LookLicense is not a report and not a score. Digits stay confirm-ticket licensed. Heat stays coupling-ticket licensed.

## Six graphs

| Graph | Licenses | Attach |
|---|---|---|
| Ticket provenance | reuse / remint / refuse | `ConfirmTicketBook` + `board_why` |
| Crop evidence | which existing scorebug band | `scorebug_crops_for_profile` (reorder only) |
| Same-Seq join | which `frame_seq` | `LivePaint` + Ghost Stick + coupling ticket |
| Refuse chain | after a refuse, what to try | `board_why` + `FREEZE_KINDS` |
| Scale stack | which timescale may request a look | CIVIF tick → phrase → drive → session |
| Negative evidence | emptiness as skip/redirect | `NO_CLAIM_REASONS`, blank BGR, `dest_denied` |

## LookLicense record

`LookLicense`: `id`, `clock_ns`, `session_id`, `graph`, `kind`, `permits`, `refuses`, optional `source_ticket_id` / `frame_seq` / `crop_hash`, `plane=qoresence-observation`.

`make_license(...)` returns `None` when the graph/kind is unknown, the payload has score digits, or the write names a frozen field (`qortroller-truth`, wrap dest, score keys, …).

JSONL: `logs/pilot/look_licenses.jsonl` (override `QORESENCE_LOOK_LICENSES_PATH`).

When `--learning-edge` is also on, a LookLicense may mint an existing constraint kind (`crop_band` | `schedule_skip` | `freeze_weight` | `hysteresis`). No new constraint kinds.

## Look gate (enforce)

`qoresence/graphs/look_gate.py` is the live seeing-path latch. Flag off → every permit is True.

| Permit | Refuses when the matching graph is on |
|---|---|
| `permit_confirm_look` | Same-Seq `seq_skew` / `plane_dim`; blank / no_frame; refuse-chain `schedule_skip` |
| `permit_ocr_look` | Same-Seq `seq_skew` / `plane_dim` |
| `permit_confirm_mint(reuse=True)` | identity stale / refuse-chain mint block; scale_tick / no active drive |

`score_changed` / `menu_exit` / `first_lock` / `force` still run confirm VLM HTTP. Tick HTTP also runs whenever `has_frame` and not blank — graphs must not skip the seeing-path. `scale_tick` / no active drive HOLDs reuse mint/speech via `permit_confirm_mint`, never `schedule()`. Refuse-chain `schedule_skip` naming confirm (quota / auth / suspicious) still refuses HTTP. The gate is query-only on the hot path — it does not append JSONL.

CIVIF ticks call `note_tick_peek` (no JSONL). Opening a drive on `SessionTimeline` escalates to drive-scale confirm (after the timeline lock). Closing the drive drops back to tick. `split_chapter_units` drops skipped chapter kinds when `--look-graphs` is on, even if `--learning-edge` is off.

When both flags are on, a refuse license may mint an existing `LearningConstraint` kind from the latest seeing-path ticket.

Same-Seq `classify_join` does not append JSONL when `(kind, live_seq, widget_seq, hid_seq)` is unchanged. LIVE paint at 30–60 fps can re-read the same frame without growing the license log.

## Operator snapshot

`look_gate.snapshot()` is query-only (no JSONL). Flag off → `None` (omit the keys). Flag on → `/health` exposes `look_scale`, `look_join`, `look_permit_confirm`, `look_refuse`. Closeout adds `look_gate` with the same four fields. No ticket ids. No score digits.

## Lock rule

Record after `ConfirmTicketBook` / lobe locks release. Never `emit_raw` from a graph. Never acquire a lobe lock in a subscribe callback. The look gate does not take a lobe lock.

## Operator

```powershell
# default: identical to main (no look-license I/O)
python -m qoresence.cli --play --deck

# opt-in next-look graphs
python -m qoresence.cli --play --deck --look-graphs
# or: $env:QORESENCE_LOOK_GRAPHS=1

# both flags: licenses may feed existing learning-edge kinds
python -m qoresence.cli --play --deck --look-graphs --learning-edge
```

## Live integration

`--look-graphs` is a seeing-path latch, not a new capture owner. First live run stays on the existing `--play --deck` path; add the flag only after capture health is green.

### Apply

1. Prove the box without the flag: `python -m qoresence.cli --play --deck --streamer-fps 30` then `curl http://127.0.0.1:8765/health`. Need `state.video.age_s` < 1s, `state.video.frames` climbing, `state.fps` > 5. No `look_*` keys.
2. Stop, restart with `--look-graphs` (or `$env:QORESENCE_LOOK_GRAPHS=1`). Do not add `--learning-edge` on the first live hour.
3. Same `/health` curl now includes `state.look_scale`, `state.look_join`, `state.look_permit_confirm`, `state.look_refuse`. Those keys are omitted when the flag is off.
4. Watch `logs/pilot/look_licenses.jsonl` (override `QORESENCE_LOOK_LICENSES_PATH`). Same-Seq does not append when `(kind, live, widget, hid)` is unchanged. Tick peek writes no JSONL.
5. Confirm digits still require a seeing-path mint: `has_confirm_ticket` + `score_vlm_locked`. A LookLicense never carries `home_score` / `away_score`.
6. After the session, closeout JSON includes `look_gate` and `look_licenses_applied` only when the flag stayed on. `write_closeout` notes one `session_wrap`.

### What to read

| Signal | Healthy live | Treat as refuse |
|---|---|---|
| `look_join` | `join_ok` or `slack_hold` | `seq_skew`, `plane_dim` |
| `look_scale` | `tick` / `phrase` / `drive` (tick is legal for VLM HTTP) | not a seeing-path skip; reuse mint HOLD is `permit_confirm_mint` |
| `look_permit_confirm` | `true` when seeing-path VLM HTTP is allowed (frame present, not blank, join ok) | `false` + `seq_skew` / `plane_dim` / `schedule_skip` |
| `look_refuse` | empty | `schedule_skip`, `seq_skew`, `plane_dim` |
| `state.video.age_s` | &lt; 1s | climbing while `frames` flat — lock/cascade, not the crop graph |
| JSONL kinds | `join_ok`, `phrase_coupling`, `drive_confirm`, `reuse` | sudden `session_wrap` mid-drive (closeout should be the only wrap) |

### Dark-ship one graph

Master flag on, one env `0` to isolate a live fault: `QORESENCE_LOOK_SAME_SEQ=0`, `QORESENCE_LOOK_SCALE=0`, `QORESENCE_LOOK_CROP=0`, `QORESENCE_LOOK_REFUSE=0`, `QORESENCE_LOOK_TICKET_DAG=0`, `QORESENCE_LOOK_NEGATIVE=0`.

### Do not

- Turn the flag on from `--play` alone
- Lower DriveGraph cap / invent a second graph
- Bind `0.0.0.0` or send licenses off-box
- Treat `look_permit_confirm` as a score lock
- Enable `--learning-edge` until look JSONL and `/health` look keys stay boring for a full session
- Drop `--streamer-fps` below 30 to “fix” a refuse — if `age_s` climbs, capture the thread stacks (deadlock), then try 30 fps as a card-stress mitigation

### Rollback

Remove `--look-graphs` / unset `QORESENCE_LOOK_GRAPHS`. Behavior matches current main: no license read, no license write, crop tuples stay the same object, `/health` omits `look_*`. Keep the JSONL file as evidence; do not delete it to “clear” a refuse.
