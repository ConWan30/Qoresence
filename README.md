# Qoresence

**Local observation-plane engine for streamers and gamers.**

Qoresence turns HDMI/OBS video, DualSense HID, and game situation into a **single causal event bus** — then surfaces it through Retina Deck, native Retina Monitor, local HDMI clips, and optional ClutchBot on Twitch.

It does **not** claim humanity, act as anti-cheat, or write to chain by default. Every lobe is **OFF** until you opt in.

[![GitHub](https://img.shields.io/badge/github-ConWan30%2FQoresence-181717?logo=github)](https://github.com/ConWan30/Qoresence)
[![Docs](https://img.shields.io/badge/docs-site-blue)](https://conwan30.github.io/Qoresence/)
[![Wiki](https://img.shields.io/badge/wiki-operator%20glass-informational)](https://github.com/ConWan30/Qoresence/wiki)
[![Python](https://img.shields.io/badge/python-3.11%2B-yellow)](https://www.python.org/)

---

## What makes it novel

| Idea | Why it matters |
|------|----------------|
| **One brain → N glasses** | Situation + events once; Lens (OBS), Rail/Theater (Deck), Monitor, Twitch panel are *views* |
| **Qoresence owns the card** | Physical HDMI has one owner — Qoresence Streamer; OBS uses Browser Source for Lens only (no dual-open) |
| **FrameHub (no second capture)** | Streamer already holds BGR frames; monitor + IVC **subscribe** — never dual-open DShow |
| **Input–Video Coupler (IVC)** | DualSense edges join `clock_ns` / `frame_seq` for co-occurrence *coupling* (observation only) |
| **Two-speed ClutchBot** | `path=fast` video+input soft acts; OCR/outcome is `path=confirm` referee (never invents scores on fast) |
| **A2A bus (optional)** | Gemini scene ↔ DeepSeek chat via Quicksilver; local policy veto; does not replace OCR |
| **Local HDMI Foundry** | True capture-ring clips (`clips/*.mp4`) + optional `.buttons.json` sidecars — not Twitch Helix-only |
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
  Deck LIVE / Retina Monitor     DualSense → InputRing → IVC
         │                              │
         └──────────┬───────────────────┘
                    ▼
             RetinaEventBus → Situation / ClutchBot / A2A
                    │
    OBS (optional stream): Browser Source ONLY
    http://127.0.0.1:8765/overlay.html  — do NOT open the same physical card
```

**Planes**

| Plane | Default | Role |
|-------|---------|------|
| Capture | Opt-in per lobe | Streamer, controller, screen, outcome, visual |
| Situation | With `--play` | Score, down, clutch context |
| Operator glass | `--deck` / `--monitor` | Theater, Lens, native monitor |
| Social | `--clutchbot` | Chat, clips, predictions |
| Research | Off | Fusion, trio-retina / WASM |

---

## Recent milestones (shipped on `main`)

| Commit / theme | What landed |
|----------------|-------------|
| **Capture ownership** | Qoresence owns physical card (Pattern B); Pattern A VCam still documented |
| **Retina Deck LIVE** | Async MJPEG, lower lag, streamer console UX |
| **FrameHub + Retina Monitor** | `--monitor` native OpenCV glass; no second capture |
| **Input–Video Coupler** | InputRing + IVC; coupling bus events; clip `.buttons.json` |
| **DualSense Edge open** | Enumerate `0x0DF2` Edge; clip export 5-tuple fix |

Docs for each: [OBS_OWNS_CARD](docs/OBS_OWNS_CARD.md) · [RETINA_MONITOR](docs/RETINA_MONITOR.md) · [CONTROLLER_VIDEO_SYNC](docs/CONTROLLER_VIDEO_SYNC.md) · [ROADMAP](docs/ROADMAP.md)

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
python -m qoresence.cli --play --deck --monitor --streamer-fps 60
# Pattern A: OBS Video Capture on card + Start Virtual Camera, then --streamer-device <VCAM>
```

---

## Quickstart (Windows-first pilot)

```powershell
git clone https://github.com/ConWan30/Qoresence.git
cd Qoresence
pip install -e ".[monitor]"   # opencv for Retina Monitor
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
| http://127.0.0.1:8765/video | LIVE MJPEG |
| http://127.0.0.1:8765/api/situation | Snapshot (+ `controller` when IVC on) |

### Verify live

```powershell
# within ~10s of start:
(Invoke-RestMethod http://127.0.0.1:8765/health).state.video.has_frame
# expect True
# optional: (Invoke-RestMethod http://127.0.0.1:8765/health).state.situation
```

Hard-refresh Deck if the tab was open before restart. Session notes: [docs/PILOT_SESSION.md](docs/PILOT_SESSION.md).

**Gameplay eye:** TV / Retina Monitor (Pattern B) or OBS Preview (Pattern A). **Not** Twitch delay.

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
| `qoresence/agents/` | SituationModel, MomentScorer, ClutchBot |
| `qoresence/fusion/` | Presence fusion (optional) |
| `qoresence/trio/` | trio-retina WASM validation (optional) |

**All lobes default `enabled = False`.**

### CLI flags (high signal)

| Flag | Default | Effect |
|------|---------|--------|
| `--play` | off | Streamer + visual(local) + outcome + ClutchBot backends + deck wiring |
| `--deck` | off | Retina Deck HTTP/WS on `:8765` |
| `--monitor` | off | Native FrameHub window |
| `--controller` | off | DualSense HID + InputRing + IVC |
| `--streamer-device N` | -1 | Auto physical card by name; or fixed index; VCam only Pattern A |
| `--clutchbot` / Twitch flags | off | IRC + Helix (see clutchbot setup) |

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
| [docs/RETINA_MONITOR.md](docs/RETINA_MONITOR.md) | Native monitor / FrameHub |
| [docs/CONTROLLER_VIDEO_SYNC.md](docs/CONTROLLER_VIDEO_SYNC.md) | IVC + InputRing |
| [docs/TWO_SPEED_CLUTCHBOT.md](docs/TWO_SPEED_CLUTCHBOT.md) | Fast video+input path; OCR confirm |
| [docs/PRIORITY_INTEGRATIONS.md](docs/PRIORITY_INTEGRATIONS.md) | Timeline · prediction lifecycle · clip chapters |
| [docs/DRIVE_GRAPH.md](docs/DRIVE_GRAPH.md) | DriveGraph climax · fast↔confirm match · Why/chapters |
| [docs/A2A_CLUTCHBOT.md](docs/A2A_CLUTCHBOT.md) | Gemini↔DeepSeek A2A bus · Quicksilver Pro |
| [docs/RELEASE_HARDENING.md](docs/RELEASE_HARDENING.md) | CI localhost · latency · soak preflight |
| [docs/RETINA_DECK_UIUX.md](docs/RETINA_DECK_UIUX.md) | Lens / Rail / Theater |
| [docs/clutchbot_setup.md](docs/clutchbot_setup.md) | Twitch tokens & scopes |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Phases & versioning |
| [docs/wiki/](docs/wiki/) | Wiki source (mirrors GitHub Wiki) |
| [docs/index.html](docs/index.html) | GitHub Pages landing |

**Community:** [Wiki](https://github.com/ConWan30/Qoresence/wiki) · [Discussions](https://github.com/ConWan30/Qoresence/discussions) · [Pages](https://conwan30.github.io/Qoresence/)  
*(If wiki/discussions/pages are first-time, enable once under Settings — see [docs/GITHUB_COMMUNITY.md](docs/GITHUB_COMMUNITY.md).)*

---

## Testing

```bash
python -m pytest tests/ -q
python -m pytest tests/test_frame_hub.py tests/test_input_ring.py tests/test_ivc.py -q
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
│   ├── deck/             # Operator theater + Lens
│   ├── agents/           # ClutchBot stack
│   ├── fusion/           # Optional presence fusion
│   └── trio/             # Optional WASM path
├── tests/
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
