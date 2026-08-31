# LOOK_GRAPHS receipt

**Plane**: qoresence-observation  
**Dest**: qortroller-truth denied  
**Flag**: `--look-graphs` / `QORESENCE_LOOK_GRAPHS` default **OFF**. `--play` does not enable.

Product: observatory engine with look-license graphs. Not a self-improving agent, narrator, or playbook.

> DriveGraph remembers what happened. The unit graph decides what may run. Look-license graphs decide which look is allowed next.

## Ceiling (restated)

- No second DriveGraph / DShow / capture card
- No invented score digits on any fast path
- No HUD digits without a seeing-path confirm mint
- No Twitch or cloud LLM calls from this work
- No mid-drive publish
- Wrap dest `qortroller-truth` stays denied
- DriveGraph cap ceiling remains 96
- No new default-ON lobe
- When the flag is OFF, no license read or write
- Record after ticket-book / lobe locks release; never emit bus events from a graph

## Files touched

| File | Why |
|---|---|
| `qoresence/graphs/look_license.py` | Typed LookLicense + JSONL; frozen-field refuse |
| `qoresence/graphs/flags.py` | Master + per-graph env |
| `qoresence/graphs/ticket_provenance.py` | mint / reuse / remint / refuse |
| `qoresence/graphs/crop_evidence.py` | Reorder existing CFB/Madden bands |
| `qoresence/graphs/same_seq_join.py` | join_ok / slack_hold / seq_skew / plane_dim |
| `qoresence/graphs/refuse_chain.py` | Causal successors onto existing constraint kinds |
| `qoresence/graphs/scale_stack.py` | Tick/phrase/drive/session escalate |
| `qoresence/graphs/negative_evidence.py` | Emptiness licenses skip |
| `qoresence/core/unified_config.py` | `look_graphs: bool = False` + env |
| `qoresence/cli.py` | `--look-graphs`; not set by `--play` |
| `qoresence/vision/confirm_ticket.py` | Provenance after mint; identity_stale after lock release |
| `qoresence/vision/scorebug_crops.py` | Crop-graph reorder when flag on |
| `qoresence/vision/scoreboard_extractor.py` | Refuse / lock hooks |
| `qoresence/vision/scoreboard_extract_why.py` | Refuse + ticker-null hooks |
| `qoresence/deck/live_paint.py` | Same-Seq + blank/no_frame notes |
| `qoresence/sync/coupling_ticket.py` | Same-Seq refuse when flag on |
| `qoresence/vision/title_presence.py` | no_claim → negative evidence |
| `qoresence/vision/title_presence_wrap.py` | dest_denied → skip |
| `qoresence/pilot/closeout.py` | Optional `look_licenses_applied` only when flag on |
| `tests/test_look_graphs.py` | Offline suite |
| `docs/LOOK_GRAPHS.md` | Operator doc |

Not touched: StreamerRuntime, FrameHub ownership, Deck/Lens/Mobile chrome, Agent Society, A2A, Twitch, Pages.

## Tests run

```
python -m pytest tests/test_look_graphs.py tests/test_drive_graph.py tests/test_seeing_path_confirm.py tests/test_scorebug_crops.py tests/test_security_localhost.py tests/test_deadlock_regression.py tests/test_otel_exporter.py tests/test_live_paint.py tests/test_coupling_ticket.py tests/test_title_presence.py tests/test_ghost_stick.py tests/test_confirm_ticket.py tests/test_learning_edge.py -q
# 148 passed, 1 skipped

python -m pytest tests/ -q
# 1339 passed, 5 skipped; 2 pre-existing failures on main (glass dist ordering, session_theater board_locked) — not this branch
```

Named cases: flag off by default and `--play` does not enable; score-digit / frozen-field refuse; flag-off mint + crop tuple identity; no JSONL when off; reuse / remint / refuse edges; provenance write outside book lock; crop reorder of existing bands only; ticker-null next fallback; slack 12 join_ok, seq_skew refuses confirm; identity_swap blocks stale remint; confirm not licensed from tick; blank skip is not a crop overlay; DriveGraph confirmed TD still outranks t0 board.

## Closeout

`look_licenses_applied` is omitted when the flag is off (`closeout_applied()` returns `None`). When on, it is the list of applied license ids (may be `[]`).
