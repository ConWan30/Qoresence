# LEARNING_EDGE receipt

**Plane**: qoresence-observation  
**Dest**: qortroller-truth denied  
**Flag**: `--learning-edge` / `QORESENCE_LEARNING_EDGE` default **OFF**. `--play` does not enable.

Product: observatory engine with a learning edge. Not a self-improving agent, narrator, or playbook.

> DriveGraph remembers what happened. The unit graph decides what may run. The learning edge makes the next DriveGraph cut work from accepted evidence.

## Ceiling (restated)

- No second DShow / capture card
- No invented score digits on any fast path
- No HUD digits without a seeing-path confirm mint
- No Twitch or cloud LLM calls from this work
- No mid-drive publish
- Wrap dest `qortroller-truth` stays denied
- DriveGraph cap ceiling remains 96
- No new default-ON lobe
- When the flag is OFF, no constraint read or write

## Files touched

| File | Why |
|---|---|
| `qoresence/agents/learning_constraint.py` | Typed constraint from accepted confirm; append-only JSONL |
| `qoresence/agents/unit_graph.py` | `evaluate_unit` code gate; correction drops one unit; retry cap 3 |
| `qoresence/agents/learning_edge.py` | Flag, load/apply splitter inputs, crop overlay, resolve hook |
| `qoresence/agents/blast_radius.py` | Irreversible lanes closed regardless of climax |
| `qoresence/vision/scorebug_crops.py` | Overlay primary band only when flag on |
| `qoresence/core/unified_config.py` | `learning_edge: bool = False` + env |
| `qoresence/cli.py` | `--learning-edge`; not set by `--play` |
| `qoresence/agents/clutchbot.py` | Flag-gated record on existing score_changed resolve hook |
| `qoresence/pilot/closeout.py` | Optional `learning_constraints_applied` only when flag on |
| `tests/test_learning_edge.py` | P1–P5 offline tests |
| `docs/LEARNING_EDGE.md` | Operator doc |

Not touched: StreamerRuntime, FrameHub ownership, Deck/Lens/Mobile chrome, Agent Society, A2A, Twitch, Pages.

## Tests run

```
python -m pytest tests/test_learning_edge.py tests/test_drive_graph.py tests/test_seeing_path_confirm.py tests/test_scorebug_crops.py tests/test_security_localhost.py tests/test_deadlock_regression.py -q
# 95 passed (targeted)

python -m pytest tests/ -q
# 1322 passed, 5 skipped; 2 pre-existing failures on main (glass dist ordering, session_theater board_locked) — not this branch
```

Named cases: missing mint → none; crop_band from good confirm; score-digit payload reject; JSONL round-trip; gate green / missing mint / batch scope / merge gap; four chapters one drop three unchanged; exhausted after 3; flag-off DriveGraph summary equality; flag-on crop overlay (CFB only); confirmed TD still outranks t0 board; ticketless ignored; high climax + no ticket cannot publish / wrap truth / serialize digits.

## Closeout

`learning_constraints_applied` is omitted when the flag is off (`closeout_applied()` returns `None`). When on, it is the list of applied constraint ids (may be `[]`).
