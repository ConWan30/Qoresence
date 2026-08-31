# DriveGraph

Causal **time-DAG** over a `SessionTimeline` drive: fast heat → arm → confirm/resolve/cancel.

## Role

| Concern | How DriveGraph helps |
|---------|----------------------|
| Why strip | `phase · climax · best_label · path` |
| Chapters | `ranked_chapter_nodes` seeds REPLAY marks |
| Predictions | Prefer `try_open` when phase armed/pressure + climax ≥ 0.25 |
| Learning | Thin samples: match_rate, climax.score, phase. Typed next-run constraints: `docs/LEARNING_EDGE.md` (`--learning-edge`, default OFF). Next-look licenses: `docs/LOOK_GRAPHS.md` (`--look-graphs`, default OFF) |

**Source of truth:** SessionTimeline only (shared `clock_ns`). No parallel log.

## Edges

| Rel | Meaning |
|-----|---------|
| `precedes` | Temporal next |
| `arms` | arm → open/resolve/confirm |
| `confirms` | fast → later confirm (≤ 8s lag) |
| `cancels` | arm/open → cancel |
| `boosts` | heat within ~400ms of following act |

## API

```python
from qoresence.agents.drive_graph import DriveGraph, active_drive_graph

g = active_drive_graph()
g.phase()           # empty|pressure|armed|open|resolved|cancelled|active
g.climax_score()    # score, best_label, match_rate, has_fast_confirm
g.match_fast_confirm()
g.ranked_chapter_nodes(k=8)
g.summary()         # attached to /api/timeline as drive_graph
```

## Wiring map

```text
SessionTimeline.snapshot()
    └── drive_graph = DriveGraph.from_timeline_drive(...)
    └── why_last.line prefer g.why_line()

Deck applyWhy(timeline)
    └── prefer drive_graph.climax.best_label

chapters_after_export()
    └── merge ranked_chapter_nodes + graph_summary on sidecar

ClutchBot._maybe_act_fast tick
    └── try_open if armed + coupling + climax/phase gate

ClutchBot score_changed
    └── _log_drive_graph_sample → LearningLogger (opt-in)
```

## Node cap

`_build_edges` is O(n²). A live 2000-event dump froze Deck `/health` (2026-08-14), so builders keep a **named safety cap**: default **48**, floor 8, hard ceiling **96**. Raise with `QORESENCE_DRIVE_GRAPH_MAX_NODES` or `from_events(..., max_nodes=N)`. Unbounded graphs are refused. Summary reports `node_cap`, `nodes_truncated`, `raw_node_count`.

## Operator

```powershell
python -m qoresence.cli --play --deck --controller --streamer-device 0 --streamer-fps 60
# After fast arm + play: GET /api/timeline → drive_graph.phase / climax
```
