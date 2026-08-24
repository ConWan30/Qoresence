# MCP Glass — universal adapter for AgentGlass (Glass D)

> **One-liner:** Qoresence is the guard watching PS5 HDMI + scoreboard + controller and understanding "clutch moment." **AgentGlass** opened a localhost window at `127.0.0.1:8765`. **MCP Glass** is the universal adapter on that window so any MCP-compatible AI (Cursor, Claude, etc.) can ask Qoresence — without ever opening the capture card.

- **Module:** `qoresence/mcp` (server entry `python -m qoresence.mcp.server` / script `qoresence-mcp`)
- **Depends on:** AgentGlass (`qoresence.agents.agent_glass`) via `127.0.0.1:8765` or in-process `_get_glass()`
- **Default-off:** only works when you run with `--agent-glass`; without Deck returns `http_unreachable` hint

## Plain English

Before AgentGlass, only Deck / ClutchBot understood the game. AgentGlass added `http://127.0.0.1:8765` — "what's the score? last drive? give me a clip?" Any local program can ask.

MCP means that program can be **any AI assistant** speaking the standard [Model Context Protocol](https://modelcontextprotocol.io). The AI doesn't learn HDMI/Vision/IVC — it asks the local expert that already decoded them.

**In use:**

- "Claude, clip that touchdown" → MCP **cannot** write — operator uses Foundry/clutch `POST /api/agent/clip` (licensed write outside MCP)
- "What's my clutch factor?" → `get_situation` → `coupling` + `situation` + `last visual_context`
- "Summarize the last red-zone drive" → `get_events(since, types=presence_report,visual_context)` → causal timeline

The AI is not guessing from pixels — it queries the curated timeline.

## Where it sits: Brain → N glasses

```
PS5 HDMI → Qoresence Streamer (owns card) → FrameHub / ClipBuffer / IVC / A2A / Situation
                                   |
                     RetinaEventBus (session_id + clock_ns)
                                   |
        Lens  LIVE  Theater  Monitor  ClutchBot  AgentGlass   MCP    Streamr*
        OBS   JPEG  Deck     native   Deck feed  HTTP/WS     **new**  (exp)
                     127.0.0.1:8765 — read-only glasses, one brain
```

`mcp` reuses Glass D — no new port, no second capture open, no `0.0.0.0`.

## 17 tools (observation-only — eyes not hands)

MCP never writes MP4/sidecars. Clip export stays on licensed `POST /api/agent/clip` / clutch Foundry path, not the MCP façade.


| tool | what it does | throttle / error |
|------|--------------|------------------|
| `get_snapshot` | curated PS5 HDMI + input + game-state + coupling + video health | `max_eps_per_client` |
| `get_events` | cursor-paginated `RetinaEventBus` (`since=_agent_seq`, `types` csv, `limit` 1..500) | `max_eps_per_client` |
| `get_health` | fast liveness (`running`, `seq`, `video{age_s,frames}`, `coupling`) | — |
| `get_frame` | latest JPEG as `data:image/jpeg;base64,...` from `ClipBuffer` | **10 fps/client** → `429 frame_throttled` |
| `get_situation` | merged `situation + coupling + last visual_context` | — |
| `get_observation` | **Witness pack** — plane-tagged title/score/phrase/glass the agent *may* say; unlocked digits and localhost phone URLs stay silent | — |
| `wrap_observation` | **Research wrap** — last `title_presence` → `qoresence-research`. Grant env required. Refuses `qortroller-truth`. | — |
| `search_clips` | Foundry RAG: keyword search over `clips/*.coupling.json` (civif-v0) + chapters + buttons + graph + timeline fallback (`query`, `limit` 1..20, `kinds` csv, `coupling_min`, `drive_id`). Pad tokens only if `input.bodied`. | — |
| `coach_clip` | CIVIF observation coach for a clip stem / `*.coupling.json`. Timing and pattern withheld unless DualSense is bodied on this host. Score digits withheld unless `board_locked`. Read-only. | — |
| `narrate_clip` | Fail-closed paragraph from the same sidecar. Same withhold rules. Read-only. | — |
| `civif_live` | Live Coupled Event Record + fail-closed coach (IVC ticks). Timing/pattern withheld unless DualSense is bodied on this host. | — |
| `civif_highlights` | Rank clips by coupling / locked score / bodied input. Returns `explanation` (no invented digits). | — |
| `civif_query_clips` | Read-only filter over coupled clips (`min_coupling_score`, `board_locked_only`, `controller_bodied_only`). | — |
| `get_drive_graph` | DriveGraph for `active` or `drive_id` → `phase/climax/match_rate/nodes/why_line` | — |
| `subscribe_events` | Proactive glass: poll since cursor, returns `next_since + poll_again_ms` for live tail | `max_eps_per_client` |
| `diagnose_freeze` | Software-only triage: `video.age_s/frames/has_frame/seq` → `FROZEN/HEALTHY/NO_FRAMES` | — |

Resources: `qoresence://snapshot`, `qoresence://events?since=&types=&limit=` · Prompts: `coach_clutch`, `debug_freeze`, `speak_licensed`.

### Foundry RAG (`qoresence/foundry/index.py` — no new deps)

Scans `clips/*.mp4` + sidecars (`*.chapters.json`, `*.buttons.json`, `graph_summary.climax`), scores by keyword overlap + confirm/fast boost + coupling + recency; falls back to `SessionTimeline.recent(80)` when no clips on disk so tests/offline still answerable. Embeddings behind `QORESENCE_FOUNDRY_EMBED` later. Filters: `kinds` csv, `coupling_min 0..1`, `drive_id`, `since_clock_ns`.

### Proactive glass

`subscribe_events` is a polling tail over the same `RetinaEventBus` cursor (`since=_agent_seq`, returns `next_since`) — true push via `WS /agent/stream` if the client supports WS. `diagnose_freeze` is software-only: reads `snapshot().video` + `health()` and applies `age_s>5s` / `frames==0` from `AGENTS.md` R1/R3/R4 — never opens capture.

## Transports

| transport | command | when |
|-----------|---------|------|
| **stdio (default)** | `python -m qoresence.mcp.server` | always — stdlib JSON-RPC fallback, no `mcp` SDK required |
| **FastMCP / SSE** | `QORESENCE_MCP_USE_FASTMCP=1 python -m qoresence.mcp.server` | when `pip install -e ".[mcp]"` (`mcp>=1.0`) |

Both paths try **in-process** `get_agent_glass()` first, then **HTTP fallback** to `127.0.0.1:8765` (`/api/agent/*`). Token from `.secrets/agent_glass.token` or env `QORESENCE_AGENT_GLASS_TOKEN` / `QORESENCE_AGENT_GLASS_TOKEN_FILE` (added as `Authorization: Bearer`).

## Quickstart

```powershell
# optional SDK for SSE mode
pip install -e ".[mcp]"   # -> mcp>=1.0

# run Qoresence with Glass D (required — MCP has no capture of its own)
python -m qoresence.cli --play --deck --agent-glass

# stdio smoke without Deck — expect http_unreachable hint
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python -m qoresence.mcp.server
echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_health","arguments":{}}}' | python -m qoresence.mcp.server

# local tests (seed in-process glass, no hardware)
python -m pytest tests/test_mcp.py -v
```

## Client configs — Cursor / Claude Desktop

`mcp.json` (or Claude `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "qoresence": {
      "command": "python",
      "args": ["-m", "qoresence.mcp.server"],
      "env": {
        "QORESENCE_AGENT_GLASS_HOST": "127.0.0.1",
        "QORESENCE_AGENT_GLASS_PORT": "8765"
      }
    }
  }
}
```

With token: `{ "env": { "QORESENCE_AGENT_GLASS_TOKEN_FILE": ".secrets/agent_glass.token" } }`. FastMCP SSE variant: set `"env": { "QORESENCE_MCP_USE_FASTMCP": "1" }`.

## Security & invariants

- **Localhost-only** — never binds `0.0.0.0`; `_resolve_base()` rewrites `0.0.0.0 → 127.0.0.1`. No new port — reuses Deck `8765`.
- **Never opens capture** — reads `ClipBuffer.latest_jpeg` / `RetinaEventBus` only; falls back to in-process `ClipBuffer` only when `http_unreachable`.
- **Respects Deck policy** — `allow_frame=false → 403`, `allow_clip=false → 403`; throttles `429` pass through.
- **AGENTS.md R1/R3/R4 hold** — AgentGlass appends under `RLock` but fans out outside lock; slow MCP client cannot deadlock streamer/watchdog/IVC.
- **Observation-only:** no `export_clip` on MCP — eyes not hands; no Truth-plane / authorship via MCP.
- **Timeouts:** HTTP 2 s so reads never block stdio forever.

## Troubleshooting

| symptom | fix |
|---------|-----|
| `http_unreachable` / "is Qoresence running with --agent-glass?" | start `python -m qoresence.cli --play --deck --agent-glass` and retry `get_health` |
| `frame_throttled` (429) | `get_frame` is 10 fps/client — back off 100 ms |
| `clip_rate_limited` (429) | only on licensed `POST /api/agent/clip` (not MCP) |
| `video.age_s` climbs, `frames` stalled | not the card — capture thread deadlocked; `py-spy dump --pid <pid>`, see `AGENTS.md` |
| Token 401 | `cat .secrets/agent_glass.token` present and `QORESENCE_AGENT_GLASS_REQUIRE_TOKEN=1` on Deck side |

## Live gate (blocked until USB3.0 card back)

```powershell
.\qoresence.bat --play --deck --agent-glass --streamer-fps 30
# then from MCP client:
# get_snapshot  → verify video.age_s <1s, frames climbing
# get_events    → presence_report / visual_context flowing
# POST /api/agent/clip → clips/*.mp4 (operator/Foundry — not MCP)
curl http://127.0.0.1:8765/health        # video.age_s, fps
curl http://127.0.0.1:8765/api/agent/health
```

## See also

- In-repo: `docs/AGENT_GLASS.md#mcp---universal-glass-stdio--sse-via-agentglass`, `examples/agent_watch.py`, `qoresence/mcp/server.py`, `tests/test_mcp.py`
- Wiki: [Novel-Stack](Novel-Stack) · [Retina-Deck-and-Monitor](Retina-Deck-and-Monitor) · [Operator-Runbook](Operator-Runbook) · [Roadmap](Roadmap)

