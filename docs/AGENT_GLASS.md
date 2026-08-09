# AgentGlass — localhost spectator API (glass D)

One brain → N glasses. AgentGlass is **glass D**: a read-only spectator bridge that exposes Qoresence's unified `PS5 HDMI + input + game-state` timeline via `RetinaEventBus`/`Deck` without ever opening the capture card.

- **Default OFF.** Enable explicitly: `QORESENCE_AGENT_GLASS_ENABLED=1` or `--agent-glass`.
- **Localhost-only.** Host must be `127.0.0.1` unless `require_token=true` + `token_file` bearer.
- **No capture.** Reads from `ClipBuffer` JPEG ring and `RetinaEventBus` deque only.
- **Reuses Deck port 8765** (no new port). Same pilot lock as Deck.

## Enable

```powershell
# env
$env:QORESENCE_AGENT_GLASS_ENABLED="1"
python -m qoresence.cli --play --deck --monitor --agent-glass

# explicit token file
python -m qoresence.cli --play --deck --agent-glass --agent-glass-token-file .secrets/agent_glass.token

# disable frame (situation+coupling+events only)
python -m qoresence.cli --play --deck --agent-glass --agent-glass-no-frame
```

Token: `echo my-32-char-token > .secrets/agent_glass.token` and set `QORESENCE_AGENT_GLASS_REQUIRE_TOKEN=1`.

## Config (`RetinaUnifiedConfig.agent_glass`)

| field | default | env |
|-------|---------|-----|
| `enabled` | `False` | `QORESENCE_AGENT_GLASS_ENABLED` |
| `host` | `127.0.0.1` | `QORESENCE_AGENT_GLASS_HOST` |
| `port` | `8765` | `QORESENCE_AGENT_GLASS_PORT` |
| `max_clients` | `8` | `QORESENCE_AGENT_GLASS_MAX_CLIENTS` |
| `max_eps_per_client` | `20.0` | `QORESENCE_AGENT_GLASS_MAX_EPS` |
| `max_history` | `256` | `QORESENCE_AGENT_GLASS_MAX_HISTORY` |
| `require_token` | `False` | `QORESENCE_AGENT_GLASS_REQUIRE_TOKEN` |
| `token_file` | `.secrets/agent_glass.token` | `QORESENCE_AGENT_GLASS_TOKEN_FILE` |
| `snapshot_hz` | `5.0` | `QORESENCE_AGENT_GLASS_SNAPSHOT_HZ` |
| `allow_frame` | `True` | `QORESENCE_AGENT_GLASS_ALLOW_FRAME` |
| `allow_clip` | `True` | `QORESENCE_AGENT_GLASS_ALLOW_CLIP` |
| `cors_allow_all` | `True` | — |

Validated: `host` must be `127.0.0.1` unless `require_token=true`; `snapshot_hz 1..10`; `max_clients 1..32`.

## HTTP

All endpoints are **read-only** except `/api/agent/clip` (exports local ring, rate-limited).

| method | path | auth | throttle | notes |
|--------|------|------|----------|-------|
| `GET` | `/api/agent/snapshot` | optional bearer | `max_eps_per_client` | curated: `session+situation+coupling+video+bus+seq+clock_ns` |
| `GET` | `/api/agent/events?since=&types=&limit=` | optional bearer | `max_eps_per_client` | cursor `_agent_seq`, filters `types` csv, limit 1..500 |
| `GET` | `/api/agent/health` | optional bearer | — | `running, seq, video, coupling` |
| `GET` | `/api/agent/frame` | optional bearer | **10 fps/client** (429 `frame_throttled`) | JPEG from `ClipBuffer.get_latest_jpeg()`, respects `allow_frame=false → 403` |
| `POST` | `/api/agent/clip` | optional bearer | **1 per 10s global** (429 `clip_rate_limited`) | `{"seconds": 10}` → local MP4, respects `allow_clip=false → 403` |
| `WS` | `/agent/stream` | `?token=` or `Authorization: Bearer` | — | snapshot on connect, then events + `agent_keepalive` each sec |

CORS: `Access-Control-Allow-Origin: *` on agent responses. FastAPI and stdlib fallback both wired.

## SDK

```python
import urllib.request, json, time
base="http://127.0.0.1:8765"
snap=json.loads(urllib.request.urlopen(f"{base}/api/agent/snapshot").read())
seq=snap["seq"]
ev=json.loads(urllib.request.urlopen(f"{base}/api/agent/events?since={seq}&limit=20").read())
print(ev["count"], ev["next_seq"])
```

See `examples/agent_watch.py`:

```powershell
python examples/agent_watch.py --once
python examples/agent_watch.py --types presence_report,visual_context
python examples/agent_watch.py --ws   # needs `pip install websockets`
```

## Threading invariant

Per `AGENTS.md` R1/R3/R4: AgentGlass never emits while holding `_lock` (append-only `_on_event` under `RLock`, fanout via bus subscribe callback outside lock). Presence reports emitted outside presence `RLock` so slow agent subscribers never block streamer/watchdog/IVC.
