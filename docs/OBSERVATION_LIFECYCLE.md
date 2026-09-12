# Qoresence Observation Lifecycle — experimental vertical slice

One candidate football moment, one ID, append-only revisions, shared by the
Deck review page, OBS Browser Source and AgentGlass/MCP snapshots. Default OFF.
This is an observation engine prototype, not a validated play detector or coach.

## Run locally

```powershell
$env:QORESENCE_OBSERVATIONS="1"
python -m qoresence.cli --play --deck --agent-glass
```

- Review: `http://127.0.0.1:8765/observations.html`
- OBS Browser Source: `http://127.0.0.1:8765/observations.html?overlay=1`
- JSON: `GET /api/observations` (same optional bearer check as AgentGlass)
- AgentGlass/MCP: `get_snapshot().observations`
- Durable journal: `logs/observations.jsonl`, one normalized evidence/record pair per revision.

The review/OBS page uses same-origin requests and does not store or embed tokens.
When bearer authentication is required, use an authenticated API client; the
page displays authentication-required rather than placing secrets in URLs.
FastAPI is required for these new pages/routes; stdlib fallback is not supported.
OBS consumes the Browser Source; never open the physical card a second time.

## Contracts and lifecycle

VisualContext's existing football phase vocabulary bounds a candidate:
running/passing/coverage/etc. start tracking; huddle or menu/replay/results/pause
closes it. These are detector-time estimates, not frame-exact play boundaries.
Snap alone is not a start: the existing vocabulary also uses it for preplay.
A 30-second observation timeout closes unresolved on the next visual event.
Silence or process shutdown does not invent an end boundary.

The pure reducer moves candidate → tracking → partial/confirmed/unresolved.
Closure is provisionally evaluated within a transition. Revisions preserve
previous decisions; a new active phase starts a new ID. Out-of-order evidence is
ignored rather than reopening a newer interval. Late scoreboard qualification
can revise a closed record for eight seconds, until a new candidate starts.

Confirmation means a **historical scoreboard claim** was qualified by a real
seeing-path ticket at emission. It does not confirm the play outcome or input
causation. Tickets and their qualification are frozen into the evidence before
reduction; replay does not consult the current ticket book or a model. The ticket
identifies its own frame/crop, not necessarily the phase-classifier's frame.
Historical claims must not be used as live score licenses.

Inputs remain `not_on_this_host` until DualSense HID is separately observed on
this host (DualSense on PS5 is Path B default). Outcome is null. See
`docs/ASTRA_SLICE_C_FOOTBALL_ADAPTER.md` for football adapter phases, blind
spots, and `QORESENCE_FOOTBALL_ADAPTER=1` (auto-select when observations on).
InputRing analysis, causal attribution, coaching, game-specific hysteresis and
frame-exact segmentation are follow-up work requiring labeled pilot evidence.

## Runtime and persistence

The bus callback only filters and enqueues to a bounded queue. A worker reduces,
journals and emits `observation_revision` outside its lock. A separate bounded
worker preserves clips. Slow disk, encoding or downstream subscribers can drop
observation evidence but cannot block the capture callback; drops are surfaced
and affected records close unresolved. Queue depth is 128; export depth is 4.

Records and revision snapshots are bounded in RAM (64 and 128 respectively).
The API returns the last 32 records; the durable journal retains normalized evidence,
the policy version, and all emitted revisions. Restart does not automatically load
old sessions into the live view. Journal errors are visible; the engine does not
claim persistence succeeded when writing fails. Recap export reads and replays the
same journal before hashing it as the `observations` envelope sidecar. Disk
retention/rotation is an operator responsibility.

Each emitted visual event stamps `event_id` and `observation_tick` into the existing
bus event. The tick is the envelope `Tick` contract and carries the same evidence id;
the reducer's first evidence id becomes `observation_id`. Revisions add only
`observation_id` and `revision` references to those ticks. There is no second
observation identity or unrehashable Recap record.

Replay each journal evidence item through `reduce_observation`, keeping state
per session and applying clip completions to their `observation_id`. Compare each
result with the journal's recorded revision. Policy/schema versions are explicit.

Interval exports refuse incomplete/expired ring windows instead of selecting
newer gameplay. Encoding can still fail or lag; completion revisions expose that.
Clip names are `hdmi_clip_<observation_id>_r<revision>.mp4`, so a clip points to
the exact observation revision used for its interval request.
Interval-aware coupling/OTel sidecars remain available. Legacy helpers that sample
the current time (buttons, chapters, stem-audio metadata) are skipped for interval
exports. Clip files use deterministic observation IDs and the existing media route.

## Replay a session

Offline replay verifies every journaled revision without capture, network,
Quicksilver, or VLM. Frozen `detector_output` and ticket qualification in each
evidence row are the only model inputs the reducer consults.

```powershell
python -m qoresence.observation.replay logs/observations.jsonl
```

Optional: `--session-id <id>` when the file contains multiple sessions.

Live journaling can freeze detector outputs at emission when
`QORESENCE_EVENT_REPLAY=1` (default OFF). Observation runtime remains
`QORESENCE_OBSERVATIONS=1`.

## Validation and pilot gate

`python -m pytest tests/test_observation_lifecycle.py tests/test_observation_event_replay.py tests/test_observation_football_adapter.py tests/test_deadlock_regression.py`

Synthetic tests cover replay, revision immutability, duplicates, late evidence,
overflow, persistence failures, clip completion routing, missing tickets and
shared surfaces. They do not establish gameplay detection accuracy, Windows
capture performance, or OBS rendering behavior on an operator machine.

Before default enablement: label actual football sessions, measure segmentation
error and false confirmed claims, inspect missing-data behavior, and verify that
capture health remains stable while export and slow consumers are active.
