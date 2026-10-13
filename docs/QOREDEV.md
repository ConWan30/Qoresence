# Qoredev recut — offline landing envelope

Not A2ABus. Not Agent Society. Not ClutchBot. Not DualSense. Not `--play`.
Not Deck `/health`. Not PR #155.

Qoredev sequences `physical → clock → lock → glass → story` by composing a
snapshot dict into one existing `qoresence-operator-bus-1` envelope.

This recut does **not** write `/health.qoredev` or add
`GET /api/operator/qoredev`. That was the #155 cut. Do not continue #155.
Do not merge #154 or #155.

## Offline

```
python -m qoresence.operator_bus.qoredev < snapshot.json
```

`evidence.next` is the first unlicensed of physical / clock / lock / glass.
When all four license, `kind=hold` even if story is empty.

| Step | Licenses when | Stays dark when |
|------|----------------|-----------------|
| physical | `has_frame` and `age_s` < 1 | freeze / no frame / watch |
| clock | FrameHub `seq` + `clock_ns` | missing seq or clock. Empty HID is valid. |
| lock | confirm ticket **and** `score_vlm_locked` | flag-only lock, unlocked board |
| glass | clients ≥ 1 **or** snapshot `glass.js` | no SPA name and no clients |
| story | persisted events **or** honest empty | never a land ticket |

## Law

- Plane = `qoresence-observation`. Envelope = `qoresence-operator-bus-1`.
- `path=fast` never carries score digits.
- No overlay until Qoreeval signal + licensed lock.
- No DualSense / Bind / HID. No `--x-glass` / encoder / WHIP / RTMP.
- GO is not GO MERGE.

## Code

- `qoresence.operator_bus.qoredev`
- `QOREDEV_BUS_PROMPT`
- `tests/test_qoredev.py`
