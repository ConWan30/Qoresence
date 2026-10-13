# Qoredev RECUT — offline operator-bus envelope

**Status**: DRAFT — do not merge. Do not continue #155. Do not merge #154 or #155.  
**Branch**: `cursor/qoredev-recut-observation-521a`  
**Base**: `main` `7a7393f`  
**Plane**: `qoresence-observation`

## Why recut

#155 wired a new `qoredev-sequence-1` schema onto Deck `/health` and
`GET /api/operator/qoredev`. Qoredev's law is evaluation + density, not
more live schemas. Operator typed RECUT.

## This cut

- Offline composer → existing `qoresence-operator-bus-1` envelope
- `python -m qoresence.operator_bus.qoredev < snapshot.json`
- No Deck routes. No `/health` field. No filesystem stat. No `last_narrative` peek.
- No DualSense. No `--play`. No `--x-glass` / encoder / WHIP / RTMP.

## Falsify

```
python -m pytest tests/test_qoredev.py tests/test_operator_bus.py -q
ruff check qoresence/operator_bus/qoredev.py qoresence/operator_bus/prompt.py
```
