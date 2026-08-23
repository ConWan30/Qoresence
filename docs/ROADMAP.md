# Qoresence Roadmap

Local **capture → situation → operator glass → optional social** pipeline.  
Research modules (fusion, trio-retina) stay off the critical path unless opted in.

---

## Shipped milestones (2026)

### Capture ownership & Deck glass ✓
- [x] Pattern B (recommended): Qoresence owns physical card; Pattern A VCam legacy (`docs/OBS_OWNS_CARD.md`)
- [x] Retina Deck: Lens `/overlay.html`, Theater `/deck.html`, LIVE `/video`, Mobile Glass `/mobile.html`
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

### DriveGraph ✓
- [x] Time-DAG per drive: precedes / arms / confirms / cancels / boosts  
- [x] `climax_score`, `match_fast_confirm`, `ranked_chapter_nodes`  
- [x] Attached to `/api/timeline` + Deck Why preference  
- [x] Chapter merge + `graph_summary` sidecar; thin learning samples  
- [x] Docs: `docs/DRIVE_GRAPH.md`

### Title-presence & Mobile Glass ✓
- [x] Optical title lock (`plane: qoresence-observation`) wrapping `GameAutoDetector`
- [x] On with `--play` / `--stream`; `--game-profile` pin honored; `--no-title-presence` opt-out
- [x] Mobile Glass `/mobile.html` — FrameHub WebRTC, MJPEG fallback
- [x] LAN bind opt-in (`--deck-bind 0.0.0.0`); Theater QR (PC cannot open the phone browser)
- [x] Docs: `docs/TITLE_PRESENCE.md`, `docs/MOBILE_GLASS.md`, `docs/WEBRTC_LIVE.md`

### Pilot closeout schema v2 ✓
- [x] `freeze_events_by_kind` + `freeze_events_excluding_deck_lock`
- [x] Docs: `docs/PILOT_MONITOR.md`, `docs/build_receipts/FREEZE_COMPARABILITY.md`

### Native Glass (Mobile Glass phase 2) ✓
- [x] PWA shell: `manifest.webmanifest`, `sw.js`, maskable icons, deck routes (`/api/discover`, `/manifest.webmanifest`, `/sw.js`, `/icons/{name}`)
- [x] Deck-side mDNS broadcaster `qoresence/deck/mdns.py` (`_qoresence._tcp`, loopback no-op, `zeroconf` optional)
- [x] Android cinema app (Capacitor, `io.qoresence.glass`): `/live.jpg` pump (WebView cannot play MJPEG), clutch HUD, PiP, keep-awake, Save clip → PC
- [x] Native plugins: `QoreMdnsPlugin`, `QoreBackgroundPlugin` + `QoreForegroundService`, `QoreCinemaPlugin`
- [x] `/api/situation` exposes top-level `coupling.climax_score` (clutch no longer silent)
- [x] PWA pairing gate skips when served from the deck (localhost UX regression fixed)
- [x] Docs: `docs/NATIVE_GLASS.md`; tests: `tests/test_mobile_glass_pwa.py`

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
- [x] Deck feed + local HDMI clip backends (offline-capable) — **this is the product path**
- [x] Twitch IRC / Helix / EventSub backends (leftover, default-OFF, not a product route)
- [x] Session memory / learning hooks

## Phase 4 — Packaging & polish (partial)
- [x] CLI entry + `--play` / `--stream` presets
- [x] Game profile aliases, personas
- [x] System tray / status indicator (`--tray`, pystray)
- [x] Windows one-liner launcher (`qoresence.bat`)

## Phase 5 — Game profile expansion
- [x] Richer football event vocabulary (touchdown, field_goal, safety, 2PC, red_zone, 2-min warning)
- [x] FPS profiles beyond CoD (Valorant, Apex Legends, Fortnite)
- [x] Community game-profile SDK (YAML + Python API, `--profiles-list`)

## Phase 6 — Operator glass polish
- [x] Deck `controller` strip in Theater UI (APM, triggers, stick, sync)
- [x] Monitor HUD layout presets (`--monitor-preset`, `p` key cycle)
- [x] DualSense Edge HID report decode harden (BT/USB, deadzone, debounce)
- [x] Pattern A lag auto-tune hints from measured VCam age

## Phase 7 — Trio-inspired architecture improvements
- [x] Gap analysis: Trio principles mapped to Qoresence (docs/TRIO_GAP_ANALYSIS.md)
- [x] Evidence chains (P4): structured citation for every A2A decision
- [x] Router must-fire predicates (P2): typed predicate set + decision log
- [x] Tool registry (P3): query-memory + zoom-redetect with depth bound

## Phase 7.5 — Profile pin + score lock + lobe health
- [x] Operator profile pin persistence (`~/.qoresence/last_game_profile`, `QORESENCE_GAME_PROFILE` env)
- [x] First-run NCAA fallback is not a pin (optics can still lock the live title)
- [x] SituationModel honors operator pin — title-presence observes but does not yank
- [x] Local HUD digit lock (fail-closed, template-free 0–9 classifier, no invented scores)
- [x] Outcome lobe heartbeat (prevents temporal_desync on stable game state)
- [x] A2A veto tuning (25s cooldown, 40-char near-duplicate, relaxed digit check)

## Phase 7.6 — OpenTelemetry causal tracing (shipped)
- [x] `OtelExporter` — non-blocking bus subscriber, bounded drop-oldest queue
- [x] Causal `bus.cascade` spans to local OTLP / Jaeger
- [x] DualSense / IVC coupling gauges and span attributes
- [x] Re-entrancy smoke alarm for A2A/Presence deadlock class
- [x] Trace-annotated clips (`.otel.json` sidecar with `jaeger_urls`)
- [x] Per-frame coupling sidecars (`.coupling.json` with `coupling_history` + `input_ring_events`)
- [x] Docs: `docs/OTEL.md`, `docs/CONTROLLER_VIDEO_SYNC.md`

## Retina Stem (local program, not OBS)
- [x] Stem Conductor on `--play` (`stem_program` = watch/prime/armed/hold/encode)
- [x] `--stem-program` Monitor Program-out (replaces OBS Preview on Pattern B)
- [x] `--stem-audio` capture-card audio allow-list (never a laptop mic)
- [x] `--stem-record` opt-in session mux (not a 1.0 gate)
- [x] Docs: `docs/STEM.md`, wiki Retina-Stem

## Phase 8 — Research (optional)
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
| **0.5.0** | **Deck LIVE + Qoresence owns card + FrameHub monitor + IVC** |
| 0.6.0 | Profile expansion + Edge HID polish + operator glass (Phase 4/6 done) |
| **0.7.0** | **OpenTelemetry causal tracing + per-frame coupling sidecars + re-entrancy smoke alarm** ← current main |
| 1.0.0 | Stable local ClutchBot (Deck + HDMI clips) + operator glass release |

---

## Non-goals

- Second `VideoCapture` opened “for sync”
- Rebuilding OBS (scenes, RTMP, Virtual Cam, Browser Source host)
- Twitch-delay as master clock
- Truth-plane / anti-cheat product claims
- Cloud storage of raw biometrics by default
