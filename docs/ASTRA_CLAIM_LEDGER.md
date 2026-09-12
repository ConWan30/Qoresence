# Astra — Observation claim ledger

**Status:** implemented. Default OFF via `QORESENCE_OBSERVATIONS` (unchanged).

## Goal

Every meaningful assertion on the observation review surface cites supporting
evidence. Click a statement to jump to the frame/event id (or clip) that backs it.

## Claim kinds

| Kind | Role | Rules |
|------|------|-------|
| `observation` | Direct seeing-path (e.g. licensed scoreboard) | Must cite `evidence_id` |
| `interpretation` | Resemblance / situation class | **Must** cite observation refs |
| `suggestion` | e.g. “review comparable plays” | Requires `sample_size` + `uncertainty`; no authorship or invented causation |

## Record shape (`record.ledger[]`)

```json
{
  "schema_version": "observation-claim-ledger-0",
  "claim_id": "clm-…",
  "kind": "observation",
  "observation_vs_inference": "observation",
  "statement": "Licensed scoreboard observation: 7–3",
  "disposition": "accepted",
  "disposition_reason": "confirm_ticket_licensed_at_emission",
  "supporting_refs": [
    {"type": "evidence", "evidence_id": "4", "frame_seq": 4, "clock_ns": 4000000000}
  ],
  "detector_id": "quicksilver",
  "software_version": "0.1.0-dev",
  "model_version": "observation-detector-1"
}
```

Suggestions add `sample_size` and `uncertainty`. Dispositions: `accepted`, `withheld`, `revised`.

## Surfaces

- Journaled on each observation revision (`record.ledger`)
- `GET /api/observations` and AgentGlass `snapshot().observations`
- `observations.html` — claim buttons scroll/highlight evidence JSON

## Enable

```powershell
$env:QORESENCE_OBSERVATIONS="1"
python -m qoresence.cli --play --deck --agent-glass
# Review: http://127.0.0.1:8765/observations.html
```

## Tests

```powershell
python -m pytest tests/test_observation_claim_ledger.py -q
```

Draft until operator GO MERGE.
