# Qoresence

<p align="center">
  <img src="docs/assets/qoresence-logo.png" alt="Qoresence" width="128">
</p>


**Gaming Streaming Observatory Engine** — local-first, one clock, many glasses.

Qoresence turns HDMI video, DualSense HID, and game situation into a **single causal event bus**, then surfaces it through **Sight Glass** (Aperture Glass), native Retina Monitor, local HDMI clips, and **AgentGlass / MCP**. Chat, heat, and score digits are licensed by the **shared clock plus tickets** — not by coworker personas. The capture card is the brain; everything else is a glass. Twitch is not a product route.

| What it is | What it is not |
|------------|----------------|
| Observation of HDMI + DualSense on one monotonic clock | Anti-cheat, humanity, or eligibility claims |
| Co-occurrence, coupling, presence evidence | Live path into QorTroller / PoAC / `*-truth` |
| Empty glyphs (`□–□`) and DualSense-on-PS5 emptiness | Invented `0–0`, last-good overlay, PAD WAIT as failure |
| Local MP4 + button / coupling / OTel sidecars | Dual-opening the same capture card |
| Optional research wrap onto `qoresence-research` with a grant | On-chain by default |

Docs: [GitHub Pages](https://conwan30.github.io/Qoresence/) · [Install guide](https://conwan30.github.io/Qoresence/install.html) · [Wiki](https://github.com/ConWan30/Qoresence/wiki) · [Download](https://github.com/ConWan30/Qoresence/releases/latest)

**Qoresence Live 0.9.0** — local observatory for X. Public face: **[X @Qoresence](https://x.com/Qoresence)**. Brain stays on your machine. **Live pixels:** OBS → X Live Studio ([recipe](docs/X_LIVE_STUDIO.md)). **VOD / Timeline receipts:** future X API via default-off **X Glass** — **not shipped** ([docs/X_GLASS.md](docs/X_GLASS.md)). Do not claim `--x-glass` ships.

Every lobe is **OFF** until you opt in.

[![GitHub](https://img.shields.io/badge/github-ConWan30%2FQoresence-181717?logo=github)](https://github.com/ConWan30/Qoresence)
[![X](https://img.shields.io/badge/X-%40Qoresence-000000?logo=x)](https://x.com/Qoresence)
[![Website](https://img.shields.io/badge/website-GitHub%20Pages-blue)](https://conwan30.github.io/Qoresence/)
[![Wiki](https://img.shields.io/badge/wiki-operator%20glass-informational)](https://github.com/ConWan30/Qoresence/wiki)
[![Python](https://img.shields.io/badge/python-3.11%2B-yellow)](https://www.python.org/)

<p align="center">
  <img src="docs/assets/qoresence-social-preview.png" alt="Qoresence — one clock, N glasses" width="1200">
</p>

<p align="center">
  <a href="https://conwan30.github.io/Qoresence/">
    <img src="docs/assets/qoresence-pages.png" alt="Qoresence GitHub Pages — Aperture Glass, HOLD command bar" width="1200">
  </a>
</p>

---

## What makes it novel

| Idea | Why it matters |
|------|----------------|
| **One brain → N glasses** | Situation + events once; Lens (OBS), Sight Glass, **Session Theater**, **Mobile Glass**, Monitor, Stem are *views* |
| **Ticket-clock** | Coupling ticket licenses heat / pad–picture join. Confirm ticket + `score_vlm_locked` licenses digits. Actuators: Aperture / Bind / License / Arm — not Agent Society coworkers |
| **Aperture Glass** | One visual system: Sight Glass SPA + public GitHub Pages. Flat void, machined iron, HOLD glyphs. Never fake LIVE on the site |
| **Fail-closed speech** | Unlocked scores stay empty. DualSense on the PS5 (no laptop HID) is success, not PAD WAIT. Same-Seq: widgets match the LIVE frame or they go dark |
| **Session Theater** | `/session.html` — Now + Story + Recap over a fail-closed normalized pack; live `GET /api/session/view` and `/api/session/recap`; Open clip only for validated existing MP4s |
| **CIVIF** | Coupled Input–Video Intelligence Framework. Live ticks + clip records; `/civif.html` and `GET /api/civif/live`. Session Theater is a query over that pack — not a second capture |
| **Title-presence** | Optical title lock with a hard `plane` tag; on with `--play`; menu/pause fail-closed; does not yank an explicit `--game-profile` |
| **Qoresence owns the card** | Physical HDMI has one owner — Qoresence Streamer; OBS uses Browser Source for Lens only (no dual-open) |
| **FrameHub (no second capture)** | Streamer already holds BGR frames; monitor + IVC **subscribe** — never dual-open DShow |
| **Input–Video Coupler (IVC)** | DualSense edges join `clock_ns` / `frame_seq` for co-occurrence *coupling* (observation only) |
| **Ghost Stick** | Pad locus painted on the HDMI frame it belongs to. Default ON under `--play`. Veto when Same-Seq / coupling drops |
| **Two-speed ClutchBot** | `path=fast` video+input soft acts; OCR + DeepSeek vision is `path=confirm` referee (never invents scores on fast) |
| **A2A bus (optional)** | Quicksilver scene/chat under local policy; does **not** replace OCR / confirm tickets |
| **Local HDMI Foundry** | True capture-ring clips (`clips/*.mp4`) + `.buttons.json` / `.coupling.json` / `.otel.json` sidecars |
| **Foundry RAG** | Search past clips by chapter/buttons/graph/timeline — software-only, no capture needed |
| **OpenTelemetry (optional)** | Causal bus traces + metrics; per-clip sidecars — local OTLP, default OFF. Exporter may only enqueue |
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
 │   clip_buffer · FrameHub · OCR / DeepSeek vision · Foundry │
 └───────┬──────────────────────────────┬─────────────────────┘
         │                              │
         ▼                              ▼
  Deck LIVE (Aperture Glass SPA) DualSense-on-PS5 (empty laptop HID = success)
  Session / Mobile / Monitor     optional: DualSense USB here → InputRing → IVC
  Ghost Stick on Same-Seq LIVE
         │                              │
         └──────────┬───────────────────┘
                    ▼
             RetinaEventBus → Situation / title-presence / tickets / ClutchBot / AgentGlass / MCP
                    │
    Coupling ticket  → heat / pad–picture (fast)
    Confirm ticket   → score digits (confirm + score_vlm_locked)
                    │
    OBS (optional stream): Browser Source ONLY
    http://127.0.0.1:8765/overlay.html  — do NOT open the same physical card
    Audience live to X (optional): OBS Custom RTMP → X Live Studio
      — not a Qoresence encoder; see docs/X_LIVE_STUDIO.md · product face docs/X_GLASS.md
    Deck:     http://127.0.0.1:8765/deck.html
