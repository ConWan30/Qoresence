# Astra Slice A — Durable, replayable event core

**Status:** Core merged to main via #206. Follow-up polish on `feat/obs-event-replay` (draft only). Do not merge follow-ups without operator GO.

Hang: `qoresence/observation/`. Default OFF. DualSense PS5 / Pattern B: opt-in,
no authorship, fail-closed tickets. Slice C/D/E and claim ledger are out of scope for this PR.

## What shipped

- Versioned journal rows: `schema_version=observation-journal-1` and
  `policy_version=football-observation-1`. Missing or unknown versions fail closed.
- Offline replay: `python -m qoresence.observation.replay logs/observations.jsonl`
  reads the journal (or a fixture), runs `reduce_observation`, and checks
  parity with recorded revisions. No network.
- Live `QORESENCE_OBSERVATIONS=1` freezes detector/VLM output
  (`observation_detector_output`, including `raw_response`) and seeing-path tickets into evidence.
  Replay uses those frozen fields only — not the live ticket book or a model.
- Late / out-of-order visual evidence is ignored rather than reopening a newer
  interval. Late scoreboard qualification stays inside the eight-second window
  and stops when a new candidate starts.

**Env:** offline replay needs no env. `QORESENCE_EVENT_REPLAY=1` is an extra
live freeze hook; the observations live path already freezes. Live runtime
remains `QORESENCE_OBSERVATIONS=1`.

See **Replay a session** in `docs/OBSERVATION_LIFECYCLE.md`.

Committed fixture: `tests/fixtures/observation_replay_session.jsonl`.
