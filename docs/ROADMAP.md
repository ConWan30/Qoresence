# Qoresence Roadmap

Local **capture → situation → operator glass → optional social** pipeline.  
Research modules (fusion, trio-retina) stay off the critical path unless opted in.

---

## Shipped milestones (2026)

### Capture ownership & Deck glass ✓
- [x] Pattern A: OBS owns physical card → Virtual Cam → Qoresence (`docs/OBS_OWNS_CARD.md`)
- [x] Retina Deck: Lens `/overlay.html`, Theater `/deck.html`, LIVE `/video`
- [x] Async MJPEG + latency-oriented LIVE path
- [x] Local HDMI clip buffer (Foundry) + browser-safe H.264 remux
- [x] Streamer console UX (clip dock, top bar)

### Native monitor (Phase 2) ✓
- [x] `FrameHub` process-local latest-frame slot (`seq` + `clock_ns`)
- [x] Streamer best-effort `publish` after `clip_buffer.push` (no second capture)
- [x] `--monitor` OpenCV HighGUI Retina Monitor (default OFF)
- [x] Docs: `docs/RETINA_MONITOR.md`

### Controller ↔ video sync ✓
- [x] `InputRing` — thread-safe HID edges
- [x] `InputVideoCoupler` (IVC) — lag band join to FrameHub stamps
- [x] Bus `coupling_score` (co-occurrence language only)
- [x] Clip sidecars `*.buttons.json` + Deck `buttons_summary`
- [x] Thin moment-scorer boost when coupling + clutch context
- [x] DualSense Edge `0x0DF2` enumeration open
- [x] Docs: `docs/CONTROLLER_VIDEO_SYNC.md`

### Two-speed ClutchBot ✓
- [x] `FastMomentEngine` — soft chat / clip intent / arm_prediction (`path=fast`)
- [x] OCR/outcome remains factual referee (`path=confirm`)
- [x] Fast chat never invents score digits
- [x] ClutchBot dispatches fast-then-confirm; graceful degrade without controller
- [x] Docs: `docs/TWO_SPEED_CLUTCHBOT.md`

### Priority integrations ✓
- [x] `SessionTimeline` — drive/session causal memory + why_last  
- [x] `PredictionLifecycleManager` — arm → open → resolve \| cancel on timeline  
- [x] Clip `.chapters.json` + Deck why strip + `/api/timeline`  
- [x] Docs: `docs/PRIORITY_INTEGRATIONS.md`

---

## Phase 0 — Skeleton ✓
- [x] Repo structure, README, LICENSE, pyproject, CI
- [x] Architecture + ClutchBot setup docs

## Phase 1 — Core capture bus ✓
- [x] Unified config, types, session mint, `RetinaEventBus` (JSONL + WS)
- [x] Unit tests

## Phase 2 — Capture lobes ✓
- [x] Streamer, controller, screen, outcome, visual
- [x] NCAA Football 27 & Call of Duty first-class profiles

## Phase 3 — ClutchBot MVP ✓
- [x] SituationModel, MomentScorer, ActionExecutor
- [x] Twitch IRC / Helix / EventSub backends
- [x] Deck feed + local HDMI clip backends (offline-capable)
- [x] Session memory / learning hooks

## Phase 4 — Packaging & polish (partial)
- [x] CLI entry + `--play` / `--stream` presets
- [x] Game profile aliases, personas
- [ ] System tray / status indicator
- [ ] Windows installer / one-liner launcher

## Phase 5 — Game profile expansion
- [ ] Richer football event vocabulary
- [ ] FPS profiles beyond CoD
- [ ] Community game-profile SDK

## Phase 6 — Operator glass polish
- [ ] Deck `controller` strip in Theater UI (beyond API field)
- [ ] Monitor HUD layout presets
- [ ] DualSense Edge HID report decode harden (reduce phantom edges)
- [ ] Pattern A lag auto-tune hints from measured VCam age

## Phase 7 — Research (optional)
- [ ] Fusion presence reports productization
- [ ] Trio-retina WASM path hardening
- [ ] DA / Merkle receipts (opt-in)
- [ ] Mobile companion (session monitor only)

---

## Versioning

| Version | Milestone |
|---------|-----------|
| 0.1.0 | Core bus + config |
| 0.2.0 | Outcome + visual lobes |
| 0.3.0 | ClutchBot MVP |
| 0.4.0 | Packaging + `--stream` / `--play` |
| **0.5.0** | **Deck LIVE + OBS owns card + FrameHub monitor + IVC** ← current main |
| 0.6.0 | Profile expansion + Edge HID polish |
| 1.0.0 | Stable ClutchBot + operator glass release |

---

## Non-goals

- Second `VideoCapture` opened “for sync”
- Twitch-delay as master clock
- Truth-plane / anti-cheat product claims
- Cloud storage of raw biometrics by default
