# AgentGlass

**AgentGlass** is glass D — a read-only spectator API that lets other programs ask Qoresence what is happening in the game without opening the capture card.

- Default OFF, enabled with `--agent-glass`.
- Binds to `127.0.0.1:8765` (same port as Deck).
- Optional `Authorization: Bearer` token file.
- Reads the same `RetinaEventBus` and `ClipBuffer` that the Deck uses.

## What it is for

You can build:

- Your own second-screen app.
- A coaching dashboard.
- A mobile PWA over Tailscale.
- An MCP client for Cursor/Claude.

## Main endpoints

| Endpoint | What it gives |
|----------|---------------|
| `GET /api/agent/snapshot` | full state: session, situation, coupling, video health |
| `GET /api/agent/events?since=&types=&limit=` | paginated timeline events |
| `GET /api/agent/health` | fast liveness: `age_s`, `frames`, `coupling` |
| `GET /api/agent/frame` | latest JPEG, 10 fps/client |
| `POST /api/agent/clip` | export last N seconds to local MP4, 1/10s |
| `WS /agent/stream?token=` | live stream of snapshots + events |

## Quick start

```powershell
# start Qoresence with the spectator glass
python -m qoresence.cli --play --deck --agent-glass --streamer-fps 30

# test
python examples/agent_watch.py --once
```

## Security

- Never binds `0.0.0.0` by default.
- Enable token auth with `--agent-glass-require-token` or `QORESENCE_AGENT_GLASS_REQUIRE_TOKEN=1`.
- It is a **glass** — it cannot control the capture card.

## Actuators, not coworkers

AgentGlass is a spectator surface. Product control is **Aperture / Bind / License / Arm** on the ticket-clock — not Agent Society personalities. Society stays default OFF; `--play` does not start it.

For the MCP adapter, see [MCP-Glass](MCP-Glass).
