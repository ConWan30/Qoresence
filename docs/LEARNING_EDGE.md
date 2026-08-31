# Learning edge

Observation-plane only. Qoresence is a **Gaming Streaming Observatory Engine**: one capture aperture, one clock, many read-only glasses. The engine gets sharper at seeing. It is not a narrator, a playbook, or a self-improving agent.

> DriveGraph remembers what happened. The unit graph decides what may run. The learning edge makes the next DriveGraph cut work from accepted evidence.

Flag: `--learning-edge` / `QORESENCE_LEARNING_EDGE`. Default **OFF**. `--play` does not enable this. When OFF, behavior matches current main: no constraint read, no constraint write.

## Three layers

| Layer | Type | Role |
|---|---|---|
| **A — DriveGraph** | attributed temporal causal DAG | What happened this drive. Already on main (`qoresence/agents/drive_graph.py`). Cap 48 default, floor 8, ceiling 96. |
| **B — Unit graph** | directed control-flow with gates | What may run. Four kinds only: splitter, worker, code, gate (`qoresence/agents/unit_graph.py`). |
| **C — Learning edge** | append-only constraint store | What the next splitter may read (`qoresence/agents/learning_constraint.py`, `learning_edge.py`). |

## Two return paths

| Path | When | Carries | Fixes |
|---|---|---|---|
| Correction edge | this run | rejected unit id + reason | current session — drop **that** unit only |
| Learning edge | after accept | typed constraint from a seeing-path mint | every later session — splitter inputs only |

A verdict that does not change what runs next is only a report. Do not add reports without a splitter effect.

The learning edge does **not** carry prose and does **not** rewrite worker prompts. It lands on the splitter: crop band, hysteresis window, rank weight, `try_open`, schedule skip, freeze weight.

## Constraint record

`LearningConstraint`: `id`, `created_clock_ns`, `session_id`, `drive_id`, `source_ticket_id` (required seeing-path mint), `kind`, `target`, `payload`, `evidence`, `frozen=false`, `plane=qoresence-observation`.

Kinds: `crop_band` | `hysteresis` | `rank_weight` | `try_open` | `schedule_skip` | `freeze_weight`.

JSONL: `logs/pilot/learning_constraints.jsonl` (override `QORESENCE_LEARNING_CONSTRAINTS_PATH`).

`from_accepted_confirm(...)` returns `None` when the mint is missing, the kind is unknown, the payload has score digits, or the write names a frozen field.

## Unit gate

`evaluate_unit(unit) -> CheckResult` is code, not a model. Absence of an error string is not a pass (`checks_run` must be > 0).

Fails: digits without seeing-path mint; merge expected ≠ actual; scope is a whole drive/batch; FREEZE with no kind tag; `plane` not observation.

Correction: retry cap 3 on the same unit, then `correction_exhausted`. Siblings stay. No model call to “fix” it.

## Frozen vs writable

**Frozen** (schema + tests reject writes; blast-radius lanes stay closed):

- score digit invention
- play advice as truth
- eligibility / anti-cheat / humanity
- mid-drive publish
- second capture
- wrap dest `qortroller-truth`
- confidence-as-gate
- shared worker/gate model context
- capture-thread ownership

**Writable from accepted confirms only** (optical / ticket evidence): crop bands, title-presence hysteresis windows, DriveGraph chapter-rank weights inside the existing cap, `try_open` threshold from arms that later resolved clean, schedule skip for a unit that never had a real edge, FREEZE kind weights that stay observational.

Gate on **blast radius**, not model confidence. Irreversible stays closed even when climax is high.

## File paths

| Path | What |
|---|---|
| `qoresence/agents/drive_graph.py` | Layer A |
| `qoresence/agents/session_timeline.py` | Drive construction |
| `qoresence/vision/confirm_ticket.py` | Seeing-path mint / refuse |
| `qoresence/agents/learning_constraint.py` | Typed constraint + JSONL |
| `qoresence/agents/unit_graph.py` | Gate + correction |
| `qoresence/agents/learning_edge.py` | Flag, apply, overlay |
| `qoresence/agents/blast_radius.py` | Closed lanes |
| `qoresence/vision/scorebug_crops.py` | Crop-band splitter input |
| `tests/test_learning_edge.py` | Offline suite |
| `docs/build_receipts/LEARNING_EDGE.md` | Receipt |

## Operator

```powershell
# default: identical to main (no constraint I/O)
python -m qoresence.cli --play --deck

# opt-in next-run splitter
python -m qoresence.cli --play --deck --learning-edge
# or: $env:QORESENCE_LEARNING_EDGE=1
```
