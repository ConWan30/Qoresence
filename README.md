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
| **OBS owns the card** | Physical HDMI has one owner; Qoresence consumes **OBS Virtual Camera** (Pattern A) |
| **FrameHub (no second capture)** | Streamer already holds BGR frames; monitor + IVC **subscribe** — never dual-open DShow |
| **Input–Video Coupler (IVC)** | DualSense edges join `clock_ns` / `frame_seq` for co-occurrence *coupling* (observation only) |
| **Two-speed ClutchBot** | `path=fast` video+input soft acts; OCR/outcome is `path=confirm` referee (never invents scores on fast) |
| **Local HDMI Foundry** | True capture-ring clips (`clips/*.mp4`) + optional `.buttons.json` sidecars — not Twitch Helix-only |
| **Causal event bus** | Every event carries `session_id` + `clock_ns` + `source_lobe` |

**Language:** *co-occurrence / coupling / presence evidence* — **not** legitimacy verification.

---

## Architecture (novel stack)

```text
 PS5 / console HDMI
        │
        ▼
 ┌──────────────────┐     Pattern A (recommended)
 │ OBS Video Capture│──── Start Virtual Camera
 │ (owns physical)  │
 └────────┬─────────┘
          │ VCam DShow
          ▼
 ┌────────────────────────────────────────────────────────────┐
 │              StreamerRuntime (UVC / OBS VCam)              │
 │  clip_buffer.push  ·  FrameHub.publish(frame, clock_ns)    │
 └───────┬──────────────────────────────┬─────────────────────┘
         │                              │
         ▼                              ▼
  Foundry / MJPEG LIVE           Retina Monitor (OpenCV)
  Deck /video                    FrameHub blit only
         │
         │   DualSense HID (optional --controller)
         ▼
  ControllerRuntime ──► InputRing ──► IVC (10–20 Hz)
         │                 lag band 20–120/200 ms
         ▼                      │
  RetinaEventBus ◄──────────────┘  coupling_score
  (JSONL + WebSocket)
         │
    ┌────┼────┬─────────────┐
    ▼    ▼    ▼             ▼
 Situation  ClutchBot   Overlay    optional trio-retina
 Model      Deck feed   Lens       / fusion research
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
| **OBS owns card** | Pattern A docs + Virtual Cam pilot path |
| **Retina Deck LIVE** | Async MJPEG, lower lag, streamer console UX |
| **FrameHub + Retina Monitor** | `--monitor` native OpenCV glass; no second capture |
| **Input–Video Coupler** | InputRing + IVC; coupling bus events; clip `.buttons.json` |
| **DualSense Edge open** | Enumerate `0x0DF2` Edge; clip export 5-tuple fix |

Docs for each: [OBS_OWNS_CARD](docs/OBS_OWNS_CARD.md) · [RETINA_MONITOR](docs/RETINA_MONITOR.md) · [CONTROLLER_VIDEO_SYNC](docs/CONTROLLER_VIDEO_SYNC.md) · [ROADMAP](docs/ROADMAP.md)

---

## Quickstart (Windows-first pilot)

```powershell
git clone https://github.com/ConWan30/Qoresence.git
cd Qoresence
pip install -e ".[monitor]"   # opencv for Retina Monitor

# 1) OBS: physical capture → Start Virtual Camera
# 2) List devices; pick OBS Virtual Camera index
python -m qoresence.cli --streamer-list

# 3) Play stack — Deck theater + Lens overlay
python -m qoresence.cli --play --deck --streamer-device <OBS_VCAM> --streamer-fps 30

# 4) Optional: native monitor + DualSense coupling
$env:QORESENCE_IVC_LAG_HI_MS = "200"
python -m qoresence.cli --play --deck --monitor --controller --streamer-device <OBS_VCAM> --streamer-fps 30
```

| URL | Glass |
|-----|--------|
| http://127.0.0.1:8765/deck.html | Ghost Theater / Rail |
| http://127.0.0.1:8765/overlay.html | Clutch Lens (OBS Browser Source) |
| http://127.0.0.1:8765/video | LIVE MJPEG (ops; not aim glass) |
| http://127.0.0.1:8765/api/situation | Snapshot (+ `controller` when IVC on) |

**Gameplay eye:** OBS Preview (physical card). **Not** Twitch delay. **Not** Deck LIVE as primary aim.

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
| `--streamer-device N` | 0 | Prefer OBS VCam index under Pattern A |
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

## Documentation map

| Doc | Topic |
|-----|--------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Core design |
| [docs/OBS_OWNS_CARD.md](docs/OBS_OWNS_CARD.md) | Capture ownership Pattern A/B |
| [docs/RETINA_MONITOR.md](docs/RETINA_MONITOR.md) | Native monitor / FrameHub |
| [docs/CONTROLLER_VIDEO_SYNC.md](docs/CONTROLLER_VIDEO_SYNC.md) | IVC + InputRing |
| [docs/TWO_SPEED_CLUTCHBOT.md](docs/TWO_SPEED_CLUTCHBOT.md) | Fast video+input path; OCR confirm |
| [docs/PRIORITY_INTEGRATIONS.md](docs/PRIORITY_INTEGRATIONS.md) | Timeline · prediction lifecycle · clip chapters |
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
