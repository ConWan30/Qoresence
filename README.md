# Qoresence

**Gaming Streaming Observatory Engine** — local-first, one clock, many glasses.

Qoresence turns HDMI/OBS video, DualSense HID, and game situation into a **single causal event bus**, then surfaces it through Retina Deck, native Retina Monitor, local HDMI clips, optional ClutchBot on Twitch, and **AgentGlass / MCP** for any AI agent. The capture card is the brain; everything else is a glass.

| What it is | What it is not |
|------------|----------------|
| Observation of HDMI + DualSense on one monotonic clock | Anti-cheat, humanity, or eligibility claims |
| Co-occurrence, coupling, presence evidence | Live path into QorTroller / PoAC / `*-truth` |
| Local MP4 + button sidecars; optional Twitch agent | Dual-opening the same capture card |
| Optional research wrap onto `qoresence-research` with a grant | On-chain by default |

Docs: [GitHub Pages](https://conwan30.github.io/Qoresence/) · [Install guide](https://conwan30.github.io/Qoresence/install.html) · [Wiki](https://github.com/ConWan30/Qoresence/wiki) · [Download](https://github.com/ConWan30/Qoresence/releases/latest)

Every lobe is **OFF** until you opt in.

[![GitHub](https://img.shields.io/badge/github-ConWan30%2FQoresence-181717?logo=github)](https://github.com/ConWan30/Qoresence)
[![Website](https://img.shields.io/badge/website-GitHub%20Pages-blue)](https://conwan30.github.io/Qoresence/)
[![Wiki](https://img.shields.io/badge/wiki-operator%20glass-informational)](https://github.com/ConWan30/Qoresence/wiki)
[![Python](https://img.shields.io/badge/python-3.11%2B-yellow)](https://www.python.org/)

<p align="center">
  <a href="https://conwan30.github.io/Qoresence/">
    <img src="docs/assets/qoresence-pages.png" alt="Qoresence GitHub Pages website" width="1200">
  </a>
</p>

---

## What makes it novel

| Idea | Why it matters |
|------|----------------|
| **One brain → N glasses** | Situation + events once; Lens (OBS), Rail/Theater, **Mobile Glass**, Monitor, Twitch panel are *views* |
| **Mobile Glass** | Phone HTML at `/mobile.html` — FrameHub WebRTC (MJPEG fallback). Phone is a view. LAN bind opt-in; Theater QR when bind is on |
| **Title-presence** | Optical title lock with a hard `plane` tag; on with `--play`; menu/pause fail-closed; does not yank an explicit `--game-profile` |
| **Qoresence owns the card** | Physical HDMI has one owner — Qoresence Streamer; OBS uses Browser Source for Lens only (no dual-open) |
| **FrameHub (no second capture)** | Streamer already holds BGR frames; monitor + IVC **subscribe** — never dual-open DShow |
| **Input–Video Coupler (IVC)** | DualSense edges join `clock_ns` / `frame_seq` for co-occurrence *coupling* (observation only) |
| **Two-speed ClutchBot** | `path=fast` video+input soft acts; OCR/outcome is `path=confirm` referee (never invents scores on fast) |
| **A2A bus (optional)** | Gemini scene ↔ DeepSeek chat via Quicksilver; local policy veto; does not replace OCR |
| **Agent Society (optional, default OFF)** | Narrow ops agents (warden, auditor, coach, editor) on glass/Foundry; Quicksilver phrasing only |
| **Local HDMI Foundry** | True capture-ring clips (`clips/*.mp4`) + optional `.buttons.json` sidecars — not Twitch Helix-only |
| **Foundry RAG** | Search past clips by chapter/buttons/graph/timeline — software-only, no capture needed |
| **OpenTelemetry (optional)** | Causal bus traces + metrics; per-clip `.otel.json` + `.coupling.json` sidecars — local OTLP, default OFF |
| **Causal event bus** | Every event carries `session_id` + `clock_ns` + `source_lobe` |

**Language:** *co-occurrence / coupling / presence evidence* — **not** legitimacy verification.

---

## Architecture (novel stack)

```text
 PS5 HDMI → capture card (physical DShow, e.g. USB3.0 Video)
        │
        ▼
 ┌────────────────────────────────────────────────────────────┐
 │   StreamerRuntime OWNS card  (--streamer-device 0)          │
 │   clip_buffer · FrameHub · OCR · Foundry                   │
 └───────┬──────────────────────────────┬─────────────────────┘
         │                              │
         ▼                              ▼
  Deck LIVE / Mobile Glass /     DualSense → InputRing → IVC
  Retina Monitor                        │
         │                              │
         └──────────┬───────────────────┘
                    ▼
             RetinaEventBus → Situation / title-presence / ClutchBot / A2A / AgentGlass / MCP
                    │
    OBS (optional stream): Browser Source ONLY
    http://127.0.0.1:8765/overlay.html  — do NOT open the same physical card
    Phone: http://127.0.0.1:8765/mobile.html  (LAN: --deck-bind 0.0.0.0 + scan QR)
```

**Planes**

| Plane | Default | Role |
|-------|---------|------|
| Capture | Opt-in per lobe | Streamer, controller, screen, outcome, visual |
| Situation | With `--play` | Score, down, clutch context |
| Operator glass | `--deck` / `--monitor` | Theater, Lens, Mobile Glass, native monitor |
| Social | `--clutchbot` | Chat, clips, predictions |
| Spectator | `--agent-glass` | HTTP/WS API + MCP for AI agents |
| Society | `--agent-society` | Ops agents on glass (default OFF; no Twitch, no capture) |
| Research | Off | Fusion, trio-retina / WASM |

---

## Recent milestones (shipped on `main`)

| Commit / theme | What landed |
|----------------|-------------|
| **Mobile Glass + QR** | `/mobile.html` FrameHub WebRTC (MJPEG fallback); Theater copy-link + QR when `--deck-bind 0.0.0.0`; phone cannot be opened remotely |
| **Title-presence** | Hysteresis wrap on `GameAutoDetector`; on with `--play`; situation stays in sync; `--game-profile` pin honored |
| **Pilot FREEZE v2** | `freeze_events_by_kind` + `freeze_events_excluding_deck_lock` for pre/post-C3 compare |
| **Madden HUD crops** | Profile-aware scorebug bands from preexisting frames; CFB bands unchanged |
| **Capture ownership** | Qoresence owns physical card (Pattern B); Pattern A VCam still documented |
| **Retina Deck LIVE** | Async MJPEG, lower lag, streamer console UX |
| **FrameHub + Retina Monitor** | `--monitor` native OpenCV glass; no second capture |
| **Input–Video Coupler** | InputRing + IVC; coupling bus events; clip `.buttons.json` |
| **DualSense Edge open** | Enumerate `0x0DF2` Edge; clip export 5-tuple fix |
| **Deadlock hardening** | Re-entrancy guard in A2A + presence; AGENTS.md locking invariants; regression tests |
| **Streamr integration** | Publish selected events to a local Streamr node via HTTP/MQTT/WebSocket |
| **VLM score lock invariants** | Null/partial VLM does not wipe good OCR lock; VLM-locked scores override bad OCR |
| **Clip Foundry export** | MP4 + chapter sidecar smoke test; Foundry export verified |
| **A2A sparsity gating** | Ambient `scene_tick` / `video_ambient` require pressure, coupling, or high-climax must-fire |
| **Blank-frame guard** | Scoreboard extractor rejects uniform/black frames to prevent invented scores |
| **Health + A2A soak loggers** | `scripts/soak_logger.py` and `scripts/a2a_soak_logger.py` for long pilot validation |
| **Twitch ClutchBot smoke test** | IRC token → chat + optional auto-clips confirmed working |
| **MCP universal glass** | `qoresence-mcp` exposes 12 tools including fail-closed `get_observation` and `wrap_observation` (research dest only) |
| **OpenTelemetry integration** | `--otel` exports causal bus traces + controller/coupling metrics; `.otel.json` and `.coupling.json` clip sidecars; re-entrancy smoke alarm; Jaeger on localhost |
| **Foundry RAG + proactive glass** | `search_clips`/`get_drive_graph` searchable session memory (clips+chapters+DriveGraph+timeline fallback) + `subscribe_events`/`diagnose_freeze` on `127.0.0.1:8765` — software-only, no capture card |

Docs for each: [MOBILE_GLASS](docs/MOBILE_GLASS.md) · [TITLE_PRESENCE](docs/TITLE_PRESENCE.md) · [WEBRTC_LIVE](docs/WEBRTC_LIVE.md) · [OBS_OWNS_CARD](docs/OBS_OWNS_CARD.md) · [RETINA_MONITOR](docs/RETINA_MONITOR.md) · [CONTROLLER_VIDEO_SYNC](docs/CONTROLLER_VIDEO_SYNC.md) · [ROADMAP](docs/ROADMAP.md) · [PILOT_SESSION](docs/PILOT_SESSION.md) · [PILOT_MONITOR](docs/PILOT_MONITOR.md) · [clutchbot_setup](docs/clutchbot_setup.md)

---

## Capture (choose one owner)

**One physical HDMI/DShow device → one owner.** Full guide: [docs/CAPTURE_OWNERSHIP.md](docs/CAPTURE_OWNERSHIP.md)

| Goal | Pattern |
|------|---------|
| Low-lag pilot / native monitor | **B** — Qoresence owns card |
| OBS as broadcast director | **A** — OBS owns card → Virtual Cam |

```powershell
python -m qoresence.cli --streamer-list
# Pattern B (recommended): free the physical card from OBS, then:
python -m qoresence.cli --play --deck --monitor --agent-glass --streamer-fps 60
# Pattern A: OBS Video Capture on card + Start Virtual Camera, then --streamer-device <VCAM>
```

---

## Download and install (Windows)

The recommended user path is the versioned **Windows starter package** published on GitHub Releases. It includes the source, local installer, Deck/AgentGlass/MCP stack, pilot docs, and a launcher. Python 3.11+ is required; the installer creates a local `.venv` and does not include capture-card drivers or secrets.

- [Download the latest Windows package](https://github.com/ConWan30/Qoresence/releases/latest)
- [Windows installation guide](https://conwan30.github.io/Qoresence/install.html)
- Verify the SHA-256 file beside the ZIP when downloading a release.

```powershell
# From the extracted Qoresence folder
powershell -ExecutionPolicy Bypass -File .\Install-Qoresence.ps1
.\Start-Qoresence.bat
```

## Quickstart (Windows-first pilot)

```powershell
git clone https://github.com/ConWan30/Qoresence.git
cd Qoresence
pip install -e ".[pilot]"   # capture, Deck, Monitor, AgentGlass/MCP, Windows discovery
python scripts/pilot_preflight.py

# Pattern B: Close OBS Video Capture on the physical card (no dual-open)
python -m qoresence.cli --streamer-list
python -m qoresence.cli --play --deck --monitor --streamer-fps 60

# OBS (optional stream): Browser Source only → http://127.0.0.1:8765/overlay.html
```

| URL | Glass |
|-----|--------|
| http://127.0.0.1:8765/deck.html | Ghost Theater / Rail (LIVE @ 60 fps) |
| http://127.0.0.1:8765/overlay.html | Clutch Lens (OBS Browser Source) |
| http://127.0.0.1:8765/mobile.html | Mobile Glass (phone view; WebRTC / MJPEG) |
| http://127.0.0.1:8765/video | LIVE MJPEG |
| http://127.0.0.1:8765/api/situation | Snapshot (+ `controller` when IVC on) |
| http://127.0.0.1:8765/api/agent/snapshot | AgentGlass: curated state + coupling |
| http://127.0.0.1:8765/api/agent/events | AgentGlass: cursor-paginated events |
| http://127.0.0.1:8765/agent/stream | AgentGlass: live WebSocket stream |

### Verify live

```powershell
# within ~10s of start — use Write-Host so PowerShell always shows a labeled line:
$h = Invoke-RestMethod http://127.0.0.1:8765/health
Write-Host "has_frame=$($h.state.video.has_frame)  fps=$($h.state.video.target_fps)  score=$($h.state.situation.home_score)-$($h.state.situation.away_score)"
# expect has_frame=True

# open Deck (browser does not auto-open from CLI):
Start-Process http://127.0.0.1:8765/deck.html
```

**Note:** `python -m qoresence.cli --play ...` keeps running in that window (log lines only). Deck is a **browser** URL — it does not pop up by itself. Hard-refresh if the tab was open before restart.

Session notes: [docs/PILOT_SESSION.md](docs/PILOT_SESSION.md). While playing, `python scripts/pilot_monitor.py` writes `logs/pilot/closeout_*.md` ([docs/PILOT_MONITOR.md](docs/PILOT_MONITOR.md)).

**Gameplay eye:** TV / Retina Monitor (Pattern B) or OBS Preview (Pattern A). **Not** Twitch delay.

---

## Twitch ClutchBot (optional)

ClutchBot can narrate clutch moments in your Twitch channel and create clips.

### 1. Get a token
1. Make a Twitch account for your bot.
2. Log into the bot account and go to [Twitch Token Generator](https://twitchtokengenerator.com/).
3. Authorize it and copy the token.
4. Save it to `.secrets/twitch_oauth.txt` (gitignored):
   ```text
   oauth:abcdefghijklmnopqrstuvwxyz
   ```

For clips you also need the `clips:edit` scope; for predictions the broadcaster token is needed. See [docs/clutchbot_setup.md](docs/clutchbot_setup.md) for full scopes.

### 2. Launch with ClutchBot

```powershell
.\qoresence.bat `
  --play --deck --monitor --tray --a2a `
  --clutchbot `
  --clutchbot-channel <your_channel> `
  --clutchbot-username <bot_username> `
  --clutchbot-token-file .secrets\twitch_oauth.txt `
  --clutchbot-enable-clips `
  --streamer-fps 30
```

- `--clutchbot-channel` is the channel to join (streamer's login, no `#`).
- `--clutchbot-username` is the bot's login.
- `--clutchbot-enable-clips` triggers Twitch clips on clutch moments (channel must be live and token needs `clips:edit`).

### 3. Verify
1. Open `https://www.twitch.tv/<channel>/chat`.
2. Play your game.
3. On score changes, red-zone entries, turnovers, or high-coupling moments, the bot posts in chat.
4. If clips are enabled and the channel is live, the bot also posts a clip link.

---

## AgentGlass + MCP (optional)

Any MCP-compatible AI (Cursor, Claude, etc.) can query Qoresence over stdio.

```powershell
# run Qoresence with the spectator glass
.\qoresence.bat --play --deck --agent-glass --streamer-fps 30

# list tools
qoresence-mcp --help-tools

# add to Cursor / Claude Desktop mcp.json
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

Then ask the AI: *"Clip that touchdown"*, *"What's my clutch factor?"*, or *"Summarize the last red-zone drive."*

---

## Components

### Core · Lobes · Sync · Monitor · Deck · Agents

| Path | Role |
|------|------|
| `qoresence/core/` | Session, `RetinaEventBus`, unified config, types |
| `qoresence/lobes/` | streamer, controller, screen, outcome, visual |
| `qoresence/sync/` | **InputRing**, **Input–Video Coupler** |
| `qoresence/monitor/` | **FrameHub**, OpenCV Retina Monitor |
| `qoresence/vision/clip_buffer.py` | HDMI ring + Foundry export + buttons sidecar |
| `qoresence/deck/` | FastAPI Deck, overlay, LIVE, clip API |
| `qoresence/agents/` | SituationModel, MomentScorer, ClutchBot, **AgentGlass**, **MCP** |
| `qoresence/fusion/` | Presence fusion (optional) |
| `qoresence/trio/` | trio-retina WASM validation (optional) |

**All lobes default `enabled = False`.**

### CLI flags (high signal)

| Flag | Default | Effect |
|------|---------|--------|
| `--play` | off | Streamer + visual(local) + outcome + ClutchBot backends + deck wiring |
| `--game-detect` | on with `--play`/`--stream` | Incumbent `GameAutoDetector` (`--no-game-detect` to opt out) |
| `--title-presence` | on with `--play`/`--stream` | Optical title hysteresis + `plane` tag (`--no-title-presence` to opt out) |
| `--game-profile` | `ncaa_football_27` | `madden_27` (Madden NFL 27 + local NFL roster), `ncaa_football_27`, CoD / Valorant / Apex / Fortnite |
| `--deck` | off | Retina Deck HTTP/WS on `:8765` |
| `--deck-bind` | unset (host `127.0.0.1`) | Opt-in LAN listen (`0.0.0.0`) for `/mobile.html` phone glass |
| `--monitor` | off | Native FrameHub window |
| `--controller` | off | DualSense HID + InputRing + IVC |
| `--streamer-device N` | -1 | Auto physical card by name; or fixed index; VCam only Pattern A |
| `--clutchbot` / Twitch flags | off | IRC + Helix (see clutchbot setup) |
| `--agent-glass` | off | HTTP/WS spectator API (MCP-ready) |
| `--agent-society` | off (on with `--play`) | Agent Society roles; `--no-agent-society` to opt out |
| `--otel` | off | Causal traces + metrics to local OTLP; clip sidecars; Jaeger on `:16686` |

---

## What it does / doesn't

| Does | Does not |
|------|----------|
| Observe frames + HID + game situation | Claim humanity / eligibility |
| Join inputs to video by **shared clock** | Anti-cheat / legitimacy “proof” |
| Local MP4 + button sidecars | Dual-open the same capture card |
| Overlays, Deck, optional Twitch agent | Store biometrics in the cloud by default |
| Optional research trio-retina | Require on-chain for MVP |

---

## Data & privacy

| Path | Default |
|------|---------|
| **Frames / clips / timeline** | Local disk (`clips/`, `logs/`) — observation plane only |
| **Twitch** | Only if you set channel + tokens (chat / predictions) |
| **Quicksilver** | Optional: scoreboard VLM + A2A when enabled — **crops / metadata**, not continuous 60 fps upload by design |
| **Deck bind** | `127.0.0.1` only (not `0.0.0.0`) |
| **Claims** | No anti-cheat / legitimacy / “proof of humanity” |

```text
  HDMI card → Qoresence (local)
       ├─ FrameHub / Monitor / Deck LIVE   (stay on machine)
       ├─ clips/*.mp4 · logs/              (local)
       └─ optional: Twitch IRC · Quicksilver VLM/A2A (opt-in)
```

---

## Revoke / stop

1. **Stop** the CLI (Ctrl+C)  
2. **Twitch:** revoke the app token in your Twitch developer console if you used ClutchBot IRC  
3. **Keys:** remove or ignore `.secrets/*` (gitignored)  
4. **Artifacts (optional):** delete `clips/` and `logs/` if you do not want local session residue  

---

## Documentation map

| Doc | Topic |
|-----|--------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Core design |
| [docs/CAPTURE_OWNERSHIP.md](docs/CAPTURE_OWNERSHIP.md) | Pattern A (OBS) vs B (Qoresence owns card) |
| [docs/OBS_OWNS_CARD.md](docs/OBS_OWNS_CARD.md) | Extended capture operator detail |
| [docs/PILOT_SESSION.md](docs/PILOT_SESSION.md) | CFB pilot runbook + notes |
| [docs/PILOT_MONITOR.md](docs/PILOT_MONITOR.md) | P0 evidence recorder while you play |
| [docs/NFL_ROSTER.md](docs/NFL_ROSTER.md) | Madden 27 local NFL team/player names (nflverse) |
| [docs/WEBRTC_LIVE.md](docs/WEBRTC_LIVE.md) | WebRTC LIVE from FrameHub (optional) |
| [docs/RETINA_MONITOR.md](docs/RETINA_MONITOR.md) | Native monitor / FrameHub |
| [docs/OTEL.md](docs/OTEL.md) | OpenTelemetry traces, metrics, and clip sidecars |
| [docs/CONTROLLER_VIDEO_SYNC.md](docs/CONTROLLER_VIDEO_SYNC.md) | IVC + InputRing |
| [docs/TWO_SPEED_CLUTCHBOT.md](docs/TWO_SPEED_CLUTCHBOT.md) | Fast video+input path; OCR confirm |
| [docs/PRIORITY_INTEGRATIONS.md](docs/PRIORITY_INTEGRATIONS.md) | Timeline · prediction lifecycle · clip chapters |
| [docs/DRIVE_GRAPH.md](docs/DRIVE_GRAPH.md) | DriveGraph climax · fast↔confirm match · Why/chapters |
| [docs/AGENT_GLASS.md](docs/AGENT_GLASS.md) | AgentGlass / MCP spectator API |
| [docs/AGENT_SOCIETY.md](docs/AGENT_SOCIETY.md) | Agent Society (default OFF; ops roles) |
| [docs/STREAMR.md](docs/STREAMR.md) | Experimental Streamr (default OFF) |
| [docs/A2A_CLUTCHBOT.md](docs/A2A_CLUTCHBOT.md) | Gemini↔DeepSeek A2A bus · Quicksilver Pro |
| [docs/RELEASE_HARDENING.md](docs/RELEASE_HARDENING.md) | CI localhost · latency · soak preflight |
| [docs/RETINA_DECK_UIUX.md](docs/RETINA_DECK_UIUX.md) | Lens / Rail / Theater |
| [docs/clutchbot_setup.md](docs/clutchbot_setup.md) | Twitch tokens & scopes |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Phases & versioning |
| [docs/wiki/](docs/wiki/) | Wiki source (mirrors GitHub Wiki) |
| [docs/index.html](docs/index.html) | GitHub Pages landing |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to set up, test, and open PRs |

**Community:** [Wiki](https://github.com/ConWan30/Qoresence/wiki) · [Discussions](https://github.com/ConWan30/Qoresence/discussions) · [Pages](https://conwan30.github.io/Qoresence/)  
*(If wiki/discussions/pages are first-time, enable once under Settings — see [docs/GITHUB_COMMUNITY.md](docs/GITHUB_COMMUNITY.md).)*

---

## Testing

```bash
python -m pytest tests/ -q
python -m pytest tests/test_frame_hub.py tests/test_input_ring.py tests/test_ivc.py -q

# critical invariants: never break these
python -m pytest tests/test_deadlock_regression.py tests/test_security_localhost.py tests/test_agent_glass.py tests/test_mcp.py -v
```

---

## Project structure (short)

```text
Qoresence/
├── docs/                 # Architecture, runbooks, wiki source, Pages
├── qoresence/
│   ├── core/             # Bus, session, config
│   ├── lobes/            # Capture lobes
│   ├── sync/             # InputRing + IVC
│   ├── monitor/          # FrameHub + Retina Monitor
│   ├── vision/           # clip_buffer, OCR, VLM helpers
│   ├── foundry/          # Clip ring + RAG search + DriveGraph
│   ├── deck/             # Operator theater + Lens
│   ├── agents/           # ClutchBot, AgentGlass, MCP
│   ├── mcp/              # MCP server (FastMCP + stdio)
│   ├── fusion/           # Optional presence fusion
│   └── trio/             # Optional WASM path
├── tests/
├── examples/             # AgentGlass / MCP examples
└── tools/obs/            # Virtual cam & overlay notes
```

---

## License & principles

- **Observation plane** by default; research modules opt-in  
- **One physical DShow device → one owner**  
- **Streamer decides** which lobes and social backends run  
- See repository `LICENSE` for terms  

---

*Built for operators who want local, auditable, multi-glass presence — not another delayed browser preview of the same card.*
