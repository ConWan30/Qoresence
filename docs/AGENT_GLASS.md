# AgentGlass — localhost spectator API (glass D)

One brain → N glasses. AgentGlass is **glass D**: a read-only spectator bridge that exposes Qoresence's unified `PS5 HDMI + input + game-state` timeline via `RetinaEventBus`/`Deck` without ever opening the capture card.

- **Default OFF.** Enable explicitly: `QORESENCE_AGENT_GLASS_ENABLED=1` or `--agent-glass`.
- **Localhost-only.** Host must be `127.0.0.1` unless `require_token=true` + `token_file` bearer.
- **No capture.** Reads from `ClipBuffer` JPEG ring and `RetinaEventBus` deque only.
- **Reuses Deck port 8765** (no new port). Same pilot lock as Deck.
- **CIVIF** (live ticks, highlights, read-only query): [CIVIF.md](CIVIF.md). For CIVIF invariants and safety guarantees, see [CIVIF.md](CIVIF.md#civif-invariants).

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

## MCP — universal glass (stdio + SSE via AgentGlass)

Glass D is reused as **N glasses** via `qoresence/mcp` — 11 observation-only tools wrapping `AgentGlass` HTTP/in-process on `127.0.0.1:8765` without opening capture.

| tool | what it does | throttle |
|------|-------------|----------|
| `get_snapshot` | curated PS5 HDMI + input + game-state + coupling + video health | `max_eps_per_client` |
| `get_events` | cursor-paginated `RetinaEventBus` (`since=_agent_seq`, `types` csv, `limit` 1..500) | `max_eps_per_client` |
| `get_health` | fast liveness (`running`, `seq`, `video{age_s,frames}`, `coupling`) | — |
| `get_frame` | latest JPEG as `data:image/jpeg;base64,...` from `ClipBuffer` | **10 fps/client** (`429 frame_throttled`) |
| `get_situation` | merged `situation + coupling + last visual_context` | — |
| `get_observation` | **Witness pack**: plane-tagged title/score/phrase/glass the agent *may* say; unlocked digits and localhost phone URLs stay silent | — |
| `wrap_observation` | **Research wrap**: last `title_presence` → `qoresence-research` envelope. Needs `QORESENCE_WRAP_GRANT_ID`. Refuses `qortroller-truth`. | — |
| `search_clips` | **Foundry RAG**: keyword search over `clips/*.chapters.json` + `*.buttons.json` + DriveGraph summary + `SessionTimeline` fallback; filters `kinds`, `coupling_min`, `drive_id` | — |
| `get_drive_graph` | **DriveGraph**: `active` or `drive_id` → `phase/climax/match_rate/nodes/why_line` via `DriveGraph.from_events` / `from_timeline_drive` | — |
| `subscribe_events` | **Proactive glass**: poll `RetinaEventBus` with `since` cursor; returns `events + next_since + poll_again_ms` for live tail | `max_eps_per_client` |
| `diagnose_freeze` | **Software-only triage**: checks `video.age_s` / `frames` / `has_frame` / `seq`; returns `FROZEN/HEALTHY/NO_FRAMES` + AGENTS.md advice | — |

**Foundry RAG** (`qoresence/foundry/index.py`, no new deps): scans `clips/` sidecars, scores by keyword overlap + confirm/fast boost + coupling + recency; falls back to `SessionTimeline.recent(80)` when no clips on disk so tests/offline still answer. Embeddings behind `QORESENCE_FOUNDRY_EMBED` later.

**Proactive glass**: `subscribe_events` is a polling wrapper over `get_events` (true WS at `WS /agent/stream` for streaming clients); `diagnose_freeze` never opens capture — reads `snapshot().video` + `health()` and applies `age_s>5s` / `frames==0` heuristics from `AGENTS.md`.

**Transports**

- **stdio (default):** `python -m qoresence.mcp.server` — stdlib JSON-RPC fallback, no `mcp` SDK required. Works in-process (`_get_glass()`) or via HTTP fallback to `127.0.0.1:8765` (reads `.secrets/agent_glass.token`, env `QORESENCE_AGENT_GLASS_TOKEN`).
- **FastMCP SSE:** `QORESENCE_MCP_USE_FASTMCP=1 python -m qoresence.mcp.server` when `pip install mcp` is present.

```powershell
# install MCP optional
pip install -e ".[mcp]"   # -> mcp>=1.0

# run Deck with Glass D
python -m qoresence.cli --play --deck --agent-glass

# stdio smoke (no Deck): expect http_unreachable hint
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python -m qoresence.mcp.server

# in-process (tests seed AgentGlass): python -m pytest tests/test_mcp.py -v
```

**Client configs**

Cursor / Claude Desktop (`mcp.json`):

```json
{
  "mcpServers": {
    "qoresence": {
      "command": "python",
      "args": ["-m", "qoresence.mcp.server"],
      "env": { "QORESENCE_AGENT_GLASS_HOST": "127.0.0.1", "QORESENCE_AGENT_GLASS_PORT": "8765" }
    }
  }
}
```

Resources: `qoresence://snapshot`, `qoresence://events?since=&types=&limit=` · Prompts: `coach_clutch`, `debug_freeze`.

**Security:** no new port, never binds `0.0.0.0`, never opens capture, respects `allow_frame`/`allow_clip` via Deck and falls back to in-process `ClipBuffer` only when `http_unreachable`.

## Threading invariant

Per `AGENTS.md` R1/R3/R4: AgentGlass never emits while holding `_lock` (append-only `_on_event` under `RLock`, fanout via bus subscribe callback outside lock). Presence reports emitted outside presence `RLock` so slow agent subscribers never block streamer/watchdog/IVC.
