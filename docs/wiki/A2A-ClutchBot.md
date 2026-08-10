# A2A ClutchBot

A2A is an **optional** agent-to-agent bus that makes ClutchBot chat smarter under **local policy**. It does **not** replace the scoreboard referee or the fast path.

## What it does

1. **Gemini** reads the scene and describes the tension / moment.
2. **DeepSeek** rewrites that into a Twitch-ready line.
3. **Local policy** vetoes invented scores, enforces cooldowns, and blocks duplicate lines.

## Enable

```powershell
$env:QORESENCE_A2A = "1"
$env:QORESENCE_A2A_GEMINI = "1"
$env:QORESENCE_A2A_DEEPSEEK = "1"

python -m qoresence.cli --play --deck --a2a --clutchbot --streamer-fps 30
```

## When it fires

| Reason | When |
|--------|------|
| `score_changed` | home/away score changes |
| `menu_exit` | back to gameplay from menu |
| `drive_pressure` | red zone / 4th down / clutch moment |
| `coupling` | high controller+video coupling |
| `scene_tick` | ambient scene check (sparsely) |
| `video_ambient` | rare fallback |

## Policy guarantees

- **No invented scores** on the fast path.
- **45s chat cooldown** between messages.
- **Duplicate / near-duplicate veto** for ~3 minutes.
- Scoreboard OCR remains the source of truth.

## Check health

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health | Select-Object a2a
```

See [Two-Speed-ClutchBot](Two-Speed-ClutchBot) for the broader chat architecture.
