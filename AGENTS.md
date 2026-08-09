# Qoresence Agent Rules

This file is read by AI coding tools (Devin, Cursor, Claude Code, etc.).
**DO NOT** modify the invariants in this file without explicit human approval.

## Event-Bus Locking Invariants (HARD RULES)

These rules were learned from a production incident (2026-08) where the live
Deck/MJPEG feed appeared to freeze because the capture card "died". The real
cause was a **synchronous event-loop deadlock** in A2A / Presence Fusion. The
only symptom was `video.age_s` climbing while `frames` stopped increasing.

### Rule 1: Never emit a bus event while holding your own lobe lock

Any lobe that holds a `threading.Lock` (or any non-reentrant lock) while
emitting an event on `RetinaEventBus` / `A2ABus` can deadlock when a subscriber
synchronously re-enters the same lobe.

Affected files:
- `qoresence/a2a/orchestrator.py` — `maybe_trigger_from_drive`
- `qoresence/fusion/presence.py` — `_on_event` and `_emit_report`
- Any other lobe that `emit_raw` from inside a `with self._lock:` block

Correct pattern:

```python
with self._lock:
    # compute state, build message/payload
    decision = build_decision(...)
# release lock BEFORE fanning out to subscribers
self.bus.emit_something(decision)
```

### Rule 2: A2A trigger path must be re-entrancy safe

`A2AOrchestrator.maybe_trigger_from_drive` is called from event subscribers
that are themselves triggered by `router_decision` emissions. The thread-local
guard `self._tls.in_trigger` must stay in place. Do not remove it.

Removing the guard or emitting `router_decision` inside `self._lock` allows the
following cascade to deadlock the process:

```
visual → clutchbot → A2AOrchestrator.maybe_trigger_from_drive
  → bus.emit_raw(router_decision)
  → PresenceFusionEngine._on_event  (holding presence RLock)
  → _emit_report → emit_raw(presence_report)
  → clutchbot → maybe_trigger_from_drive  (same thread)
  → self._lock.acquire()                 → DEADLOCK
```

### Rule 3: Presence reports must be emitted outside the RLock

`PresenceFusionEngine._on_event` computes lobe state under `self._lock`, but
`_emit_report` / `bus.emit_raw` must run **after** the `with self._lock:` block
so that slow subscribers (ClutchBot, A2A, Monitor) do not block the streamer,
watchdog, and IVC threads.

### Rule 4: Never hold a non-reentrant lock across a subscriber callback

If a lobe emits an event while holding its lock, and a subscriber of that event
calls back into the same lobe, a self-deadlock occurs on the same OS thread.
Use `threading.RLock` only as a mitigation, not as a license to fan out under
lock.

## Regression Tests

These tests lock in the invariants above. Any PR that fails them or deletes them
must be rejected:

- `tests/test_deadlock_regression.py`

Specifically:
- `test_reentrant_trigger_from_router_decision_does_not_deadlock`
- `test_suppressed_trigger_emits_outside_lock`
- `test_presence_lock_released_during_report_fanout`
- `test_full_cascade_streamer_event_with_a2a_loop`

## Capture Card / Streamer Notes

- The USB3.0 capture card is stable at its **native 640x480 resolution** when
direct `cv2.VideoCapture(0)` tests are run.
- Qoresence currently captures at 1280x720. This is functional but may stress
some cards; if the live feed starts lagging or `age_s` climbs, lower
`--streamer-width` / `--streamer-height` or use `--streamer-fps 30`.
- `qoresence.bat` defaults to `--streamer-fps 30` with A2A enabled.

## How to Verify Live Health

```powershell
curl http://127.0.0.1:8765/health
```

Healthy values:
- `state.video.age_s` < 1.0s
- `state.video.frames` / `state.video.pushes` increasing over time
- `state.fps` > 5

If `age_s` climbs above 5s and `frames` stops increasing while the process is
still alive, use `py-spy` to capture thread stacks; the cause is almost always
a lock-ordering / event-cascade deadlock, not the capture card.

## Product Focus (NON-NEGOTIABLE)

Qoresence is a local-first ops console for gamers. Do not promote Streamr,
blockchain, DePIN, or other off-box distribution as part of the core product
story. The Streamr integration in `qoresence/streamr/` is an **experimental,
default-OFF research plugin**. It may only graduate from experimental after the
local pilot (capture health, VLM score lock, clips, Twitch chat) is proven.

