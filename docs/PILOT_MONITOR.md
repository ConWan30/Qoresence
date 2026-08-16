# Pilot monitor — P0 evidence recorder

Background sampler for a live `--play` match. It does **not** open capture, call Quicksilver, or post to Twitch. It polls localhost Deck and writes JSONL + a closeout pack under `logs/pilot/`.

This is the roadmap P0 evidence recorder (stability, scores, clips, society) — not a new lobe.

## Two-terminal flow

```powershell
# terminal A — own the card
python -m qoresence.cli --play --deck --monitor --streamer-fps 30

# terminal B — evidence
python scripts/pilot_monitor.py
# duration 0 = until Ctrl+C
```

On stop, open the newest:

```text
logs/pilot/closeout_YYYYMMDD_HHMMSS.md
logs/pilot/closeout_YYYYMMDD_HHMMSS.json
logs/pilot/session_YYYYMMDD_HHMMSS.jsonl
```

Closeout answers:

1. Did video stay alive?
2. How many score deltas and were they locked?
3. How many new clips?
4. Any FREEZE storms? Schema v2 closeouts break these out by kind (`freeze_events_by_kind`). Prefer `freeze_events_excluding_deck_lock` when comparing to pre-C3 `freeze_events`.
5. Was society noisy?

## Flags

| Flag | Meaning |
|------|---------|
| `FREEZE` | `has_frame` and `age_s > 5` for ≥3 samples |
| `NO_FRAMES` | no frame / zero frames for ≥5 samples after 30s warm-up |
| `SCORE_DELTA` | home/away pair changed |
| `SCORE_ROLLBACK` | a delta that *decreased* a side (VLM flicker, not a clip) |
| `CLIP_NEW` | new `clips/**/*.mp4` |
| `GRAPH_STALL` | situation/health slower than 2s or repeated error |
| `DECK_DOWN` | connection refused / timeout |
| `SCORE_UNLOCKED_LONG` | scores present but lock false for >120s |

## Optional in-app hook

```powershell
$env:QORESENCE_PILOT_MONITOR=1
python -m qoresence.cli --play --deck --streamer-fps 30
```

Default is **off** unless that env is `1`/`true`/`on`. Shutdown writes closeout and must not block exit more than ~2s.

## CLI

```text
python scripts/pilot_monitor.py --url http://127.0.0.1:8765 --interval 2.0 --out-dir logs/pilot --duration 0 --warm-up 30 --clips-dir clips
```

Localhost only. `--url` that is not `127.0.0.1` / `localhost` exits 2.
