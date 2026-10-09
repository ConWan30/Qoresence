# QorGraph — LOOK_SAME_SEQ_JSONL_QUIET

**Loop:** same-seq join JSONL append rate  
**Plane:** `qoresence-observation`  
**Tickets required:** none  
**May speak:** append rate, transition/sample policy  
**Must remain empty:** digits, grab loop, bounce LIVE, merge without GO MERGE

## Operator ticket

LIVE 30–60 fps advances `live_seq` every paint. `classify_join` always refreshed `_last_license` (look gate hot) but also called `append_license` on every new sig. Dedupe keyed on `(kind, live_seq, widget_seq, hid_seq)` only — so each frame grew `logs/pilot/look_licenses.jsonl` (~92MB soak) while `confirm_look_allowed` was already true.

## Implementer brief

| Rule | Behavior |
|---|---|
| Gate | Always update `_last_license` / `_last_sig` every `classify_join` call. `confirm_look_allowed` unchanged. |
| Quiet kinds | `join_ok`, `slack_hold` — append JSONL only when **kind/refuse polarity** changes, monotonic `clock_ns` gap ≥ `QORESENCE_LOOK_SAME_SEQ_JSONL_MIN_NS` (default **1e9 ns / 1s**), or `live_seq` advanced ≥ `QORESENCE_LOOK_SAME_SEQ_JSONL_EVERY_SEQ` (default **30**) since last append. |
| Loud kinds | `seq_skew`, `plane_dim` — **always** append. |
| Historic log | Never delete existing JSONL. |
| Out of scope | No score keys. No grab / DShow / LivePaint rewrite. No LIVE bounce. |

## Code

- `qoresence/graphs/same_seq_join.py` — `_last_appended_*` memory separate from gate memory.

## Env

| Variable | Default | Role |
|---|---|---|
| `QORESENCE_LOOK_SAME_SEQ_JSONL_MIN_NS` | `1000000000` | Min wall between quiet appends |
| `QORESENCE_LOOK_SAME_SEQ_JSONL_EVERY_SEQ` | `30` | Min `live_seq` delta between quiet appends |

## Tests

| Test | Asserts |
|---|---|
| `test_join_ok_jsonl_sampled_not_per_frame` | 60× `join_ok` with `live_seq=1..60` → appended lines ≪ 60 (≤3 with defaults) |
| `test_refuse_still_appends` | `seq_skew` / refuse transitions still append every time |
| `test_gate_unchanged` | `confirm_look_allowed` true for `join_ok` when JSONL is quiet |

Also: `tests/test_look_graphs.py::test_classify_join_dedups_unchanged_sig`

## Operator

DualSense PS5 — empty laptop HID is success. `--look-graphs` opt-in; default OFF. **HOLD merge** until operator GO MERGE.
