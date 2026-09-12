# Astra Slice E — Observation evaluation harness

**Status:** implemented (v0). Default OFF — does not enable observations.

## Goal

Measure whether the observation engine behaves correctly offline. Accuracy and
abstention are reported together. CI runs fixture packs without Quicksilver/VLM.

## Metrics v0

| Metric | Description |
|--------|-------------|
| `false_confirmed_claims` | **Hard-fail** — confirmed scoreboard without frozen qualification |
| `moment_boundary_error_ns` | \|expected − actual `end_ns`\| when labeled |
| `outcome_accuracy` | Match labeled `outcome_expected` (null in v0) |
| `abstention_rate` | Share of empty `uncertainty_channels` entries |
| `evidence_coverage` | Revisions with `evidence_ids` |
| `replay_consistent` | Slice A `replay_journal` parity |
| `latency_overhead` | Stub `skipped` without capture hardware |

## Run locally

```powershell
python -m pytest tests/test_observation_eval_harness.py -q
```

## Fixture packs

Location: `qoresence/evals/observation/fixtures/*.json`

Schema: `qoresence-observation-eval-0`

```json
{
  "schema": "qoresence-observation-eval-0",
  "session_id": "session",
  "journal": [ /* pack_journal_row rows from a labeled session */ ],
  "labels": {
    "allow_confirmed": true,
    "expected_final_state": "confirmed",
    "moment_boundary_end_ns": 3000000000,
    "outcome_expected": null
  }
}
```

## Add a labeled football session later

1. Run a pilot with `QORESENCE_OBSERVATIONS=1` (and optional `QORESENCE_EVENT_REPLAY=1`).
2. Copy `logs/observations.jsonl` rows for one `session_id`.
3. Add human labels: expected close time, whether confirm was allowed, outcome (usually null).
4. Save as `qoresence/evals/observation/fixtures/<name>.json`.
5. `pytest tests/test_observation_eval_harness.py` must stay green (zero false confirmed).

No live Quicksilver in CI fixtures — journals carry frozen detector/ticket evidence only.

Draft until operator GO MERGE.
