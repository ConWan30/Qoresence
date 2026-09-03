# Qoredev — landing sequence (observation plane)

Not A2ABus. Not Agent Society. Not ClutchBot. Not DualSense. Not `--play`.

Qoredev is the Grok-bot **integration & delivery lead**. This module is a
query-only receipt of the landing order already locked in
[`docs/GROK_BOT_CORPS.md`](GROK_BOT_CORPS.md):

`physical → clock → lock → glass → story`

It composes fields that already exist on `/health`. It does not emit on
`RetinaEventBus` / `A2ABus`. It does not invent score digits. Empty story is
a valid landing — HOLD density, do not mint narrative types.

## Surfaces

```
GET  http://127.0.0.1:8765/health                 →  qoredev
GET  http://127.0.0.1:8765/api/operator/qoredev
GET  http://127.0.0.1:8765/api/operator/bus/prompt?bot=qoredev
```

`qoredev.next` is the first unlicensed step among physical / clock / lock /
glass. When all four license, `next` is `hold` even if story is empty.

| Step | Licenses when | Stays dark when |
|------|----------------|-----------------|
| physical | `has_frame` and `age_s` < 1 | freeze / no frame / watch |
| clock | FrameHub `seq` + `clock_ns` | missing seq or clock. Empty HID is valid. |
| lock | confirm ticket **and** `score_vlm_locked` | flag-only lock, unlocked board |
| glass | Deck clients ≥ 1 **or** vendored SPA js | no SPA and no clients |
| story | persisted events **or** honest empty | never a land ticket |

## Law

- Plane = `qoresence-observation`. Schema = `qoredev-sequence-1`.
- `path=fast` never carries score digits. Confirm cites lock flags only.
- No overlay until Qoreeval signal + licensed lock.
- No DualSense / Bind / HID changes. No `--x-glass` / encoder / WHIP / RTMP.
- GO is not GO MERGE. Human HOLD beats every PASS.

## Code

- Receipt: `qoresence.operator_bus.qoredev`
- Prompt: `QOREDEV_BUS_PROMPT` in `qoresence.operator_bus.prompt`
- Tests: `tests/test_qoredev.py`
