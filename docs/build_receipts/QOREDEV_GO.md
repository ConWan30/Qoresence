# Qoredev GO — observation-plane landing sequence

**Status**: DRAFT PR — do not merge. Operator typed GO (not GO MERGE).  
**Branch**: `cursor/qoredev-sequence-observation-521a`  
**Plane**: `qoresence-observation`

## Intent

Operator + Qoredev GO. Query-only receipt of
`physical → clock → lock → glass → story` from existing `/health` envelopes.

## Out of scope (held)

- Merge / force-push `main`
- `--play`
- DualSense / Bind / HID
- `--x-glass` / encoder / WHIP / RTMP
- Secrets in logs or git
- New narrative types / overlay

## Landed

- `qoresence/operator_bus/qoredev.py` — sequence receipt, no `emit_raw`
- `QOREDEV_BUS_PROMPT` + `GET /api/operator/qoredev`
- `/health.qoredev` (FastAPI + stdlib)
- `GET /api/operator/bus/prompt?bot=qoredev`
- `tests/test_qoredev.py`
- `docs/QOREDEV.md`

## Falsify

```
python -m pytest tests/test_qoredev.py tests/test_operator_bus.py tests/test_deadlock_regression.py tests/test_security_localhost.py -q
```

**Cloud agent (this GO):** 39 passed (`test_qoredev` + `test_operator_bus` + deadlock + localhost security).

Empty story + licensed physical/clock/lock/glass → `next=hold`.
Score digits on a live snapshot must not appear in the receipt.
`qoredev.py` must not contain `emit_raw(`, `A2ABus(`, DualSense, `--play`, WHIP, RTMP.
