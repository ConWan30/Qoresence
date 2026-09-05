# Operator Bus — Grok bots ↔ Grok Build

Not A2ABus. Not Agent Society. Not ClutchBot.

Grok Build on the play PC and Grok Bots with their own computers share **RCP JSON envelopes** on a mailbox that only enqueues. Nothing here may `emit_raw` on `RetinaEventBus` / `A2ABus` (deadlock law).

## Why this exists

Cloud Grok Bots cannot see the capture card. They were merging crop PRs from `/health` JSON while DeepSeek was reading a 26px ticker-looking strip. The bus forces every ticket to carry evidence Grok Build can falsify (`vlm_last_crop.jpg`, `scoreboard_vlm`, `age_s`).

## Local (same machine / play PC)

```
POST http://127.0.0.1:8765/api/operator/bus
GET  http://127.0.0.1:8765/api/operator/bus
GET  http://127.0.0.1:8765/api/operator/bus/prompt
GET  http://127.0.0.1:8765/api/operator/bus/prompt?bot=qoredev
GET  http://127.0.0.1:8765/api/operator/qoredev
```

Qoredev landing sequence (physical → clock → lock → glass → story) is
query-only on `/health.qoredev` and `/api/operator/qoredev`. See
[`docs/QOREDEV.md`](QOREDEV.md). It does not emit on the event bus.

JSONL drop: `logs/operator_bus/inbox.jsonl` (bots → Grok Build), `outbox.jsonl` (Grok Build → bots).

## Remote (bot computer cannot hit loopback)

Paste the standing prompt into Qorector, then have it comment one fenced JSON envelope, or append a line to `inbox.jsonl` in a git checkout. Do not tunnel Deck off-box.

## Standing prompt

Print it:

```
python -m qoresence.operator_bus
```

Or GET `/api/operator/bus/prompt` once Deck is up. Paste that `prompt` field into Qorector as the session instruction.
