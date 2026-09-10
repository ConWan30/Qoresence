# QorGraph — Same-Seq join_ok JSONL quiet

**Plane:** `qoresence-observation`  
**Tickets required:** none  
**May speak:** append rate, transition/sample policy  
**Must remain empty:** digits, grab loop, bounce LIVE, merge without GO MERGE

## Problem

`classify_join` refreshed the look gate every LIVE paint but appended JSONL on every `live_seq` advance. At 30–60 fps that flooded `look_licenses.jsonl` (~92MB soak) while the gate was already hot.

## Contract

| Kind | JSONL |
|---|---|
| `join_ok`, `slack_hold` | Sampled: append on kind/refuse polarity change, ≥ `QORESENCE_LOOK_SAME_SEQ_JSONL_MIN_NS` (default 1e9 ns), or ≥ `QORESENCE_LOOK_SAME_SEQ_JSONL_EVERY_SEQ` (default 30) since last append |
| `seq_skew`, `plane_dim` | Always append |

`_last_license` / `confirm_look_allowed` update every call. Historic JSONL is never deleted.

## Tests

- `tests/test_same_seq_jsonl_quiet.py`
- `tests/test_look_graphs.py::test_classify_join_dedups_unchanged_sig`
