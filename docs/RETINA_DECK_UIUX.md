# RETINA DECK — Novel Overlay / Dashboard for Qoresence
> 2026-08-06 21:25 — "Gamers still see Twitch, but access Qoresence purpose"
> One brain, three glasses. Invisible when boring, exquisite when clutch.

## Thesis: Clutch Glass, Not Chrome

Standard overlays **cover** gameplay. Standard dashboards make you **alt-tab away**.
**Retina Deck** is perceptual UI: **opacity = tension**. Stream stays full-bleed 92-100%. Qoresence lives in the periphery — like a fighter-jet HUD.

18% width max. Spring motion 0.8s. Frosted glass over Field #1A3A2A. You play. Deck whispers only when it matters.

## One Brain → Three Surfaces

```
[USB3.0 Video idx0 DSHOW 1280x720@30] -> StreamerRuntime (eye-check 1.84MB, person BLOCK)
 -> VisualRuntime 6fps (heuristic 5112e31 -> hysteresis 3/5 992318e -> ONNX ee834e1 p50 1.12ms)
 -> FootballScoreboardExtractor 383L (bottom-center HUD -> score/quarter/clock/down)
 -> SituationModel + win_probability + MomentScorer/ClipWorthiness
 -> RetinaEventBus --+--> ClutchBot -> Quicksilver Pro nemotron-3.5-lightning @ https://api.quicksilverpro.io/v1 -> Twitch chat/clip/prediction
                     +--> ws://localhost:8765/retina --+--> A) Clutch Lens [OBS Browser Source]
                     +--> trio-retina batch 30s EvmLogPayload merkle    +--> B) Retina Rail [Local Deck + Twitch Extension]
                                                         +--> C) Ghost Replay [3s memory]
```

### A) Clutch Lens — In-Game HUD (OBS Browser Source, transparent 1920x1080)

**OBS setup (required):** Sources → **+** → **Browser**

| Field | Value |
|-------|--------|
| **URL** | `http://127.0.0.1:8765/overlay.html` — **not** `file:///…` |
| Width × Height | `1920` × `1080` |

`file://` breaks same-origin WS → FIN_WAIT_2 thrash and `/health` `clients:0`. See `tools/obs/README.md`.

Lives **on** the game, never **over** the ball. Bottom 8% safe area, 80px tall max.

| Element | When | Design |
|---|---|---|
| **Momentum Ribbon** | Always, 8% opacity | 1920x4px top edge. Green -> Gold gradient = win prob 0-100%. Pulses on wp_swing >0.08. Boring drive = flat gray. |
| **Down Pill** | playclock <15s or 3rd/4th down | Center-bottom pill: `3rd & 2 • Q3 00:42 • 14-7` Frosted glass, JetBrains Mono 14, fade 0.8s in / 1.2s out. OCR-grounded. |
| **Clutch Spark** | ClipWorthiness >0.75 + wp_swing >0.12 | One word + icon: `HOLD 🛡️` / `STRIKE ⚡` / `ICE 🧊` 96px bold, spring 0.9->1.0, lives 2.5s. No spam. |
| **Privacy Eye** | Boot 2s only | `FIELD verified • local • not pushed` + thumbnail. Then gone. Proves Trio verifiable layer. |

**Novel rule:** Lens opacity = clip_worthiness. Boring = 0%. Clutch = 100%. You *feel* tension before you read it.

### B) Retina Rail — The Drawer (The Innovation)

**Accessible while playing. Never alt-tab.** 360px drawer slides from right edge.

- **Local:** Tauri/Web deck at `http://localhost:8765/deck` — hotkey `Ctrl+Shift+R` or controller `Share+Options`. Game stays 88% visible (18% width, backdrop blur 92%). Click outside -> vanishes.
- **Twitch:** Extension Panel 320px + Video Overlay (same ribbon/pill, viewer opt-in "Retina ON"). No install for viewer. Mirrors ws via EBS, verified by trio-retina payload_hash if enabled.
- **4 cards, no scroll while playing:**

1. **Situation Strip (64px)** — `LOU 14 - GT 7 | Q3 3:12 | 2nd & 6 @ GT34 | WP 58%→71%` Tap -> ClutchBot `enhance_message()` TTS whisper (Quicksilver 2.61s, template fallback).
2. **Clutch Feed (3 items max)** — reverse-chronological only on TRIGGER_ONSET/OUTCOME_EVENT. `00:42 3rd&2 CONVERTED • Clip • Predict` — tap = clip(), long-press = start_prediction() (respects 3-6 msg/min).
3. **Foundry (one button)** — `Make Clip (last 30s)` -> Helix clip + auditable trail: `payload_hash 0x… events_root merkle block #28431902` — proof, not just video.
4. **Trail Dot (12px)** — `● Local ONNX 1.12ms p50 • trio-retina 30s • eval 1.0` — glanceable.

**Novel interaction: Hover Scrub.** Hover any feed item -> Ghost Replay previews underneath without leaving game.

### C) Ghost Replay — 3s Memory

After UNKNOWN->FOOTBALL transition (play end), Deck shows 3s scrub bar with retina annotations: Down Pill at 0s, Spark at 1.5s. Scrub = see what VLM saw. Built from `logs/session_*.jsonl` replay via `eval/eval_session.py` — no extra capture.

## Design System: Stadium Glass

- **Palette:** Ink #0A0E14, Field #1A3A2A, Chalk #E8EDF0, Clutch Gold #F5C542, Alert Red #E84C3D. All 12-92% opacity over video.
- **Type:** JetBrains Mono 12/14 for data, Inter 16 Semibold for Spark. Max 18 chars per card while playing.
- **Motion:** spring(0.8s mass 0.9 damping 12) — ESPN lower-third, not PowerPoint. Ribbon heartbeat 0.9s during 2-min drill.
- **Sound:** Optional 80ms tick at wp_swing >0.15, -22dB. Hear clutch without looking.
- **A11y:** 7:1 contrast over field green (tested eye_verify.jpg mean 67.9). D-pad navigable.

## UX While Playing (Controller in Hand)

1. Boot: `--play` -> USB3.0 Video -> eye-check 2s -> Lens ribbon fades in. No terminal.
2. Drive: Call play. Lens shows Pill only on 3rd down. Otherwise clean.
3. Clutch: 3rd&2 conversion -> Spark `CHAINS ⚡` + ClutchBot "Huge 3rd down! Chains move!" in Twitch (viewer sees same Pill). Tap Foundry if you want clip.
4. Viewer: Clicks Extension "Retina ON" -> sees your Ribbon/Pill read-only, no cost to you.
5. Post-game: Deck expands to `/deck/review` -> full eval histogram p50 1.12 p95 1.98 p99 2.64, CLEAN 1.0 precision, searchable feed. `logs/` stays gitignored.

## Why Novel vs Existing

| Existing | Retina Deck |
|---|---|
| StreamElements = 12 stats, covers game, alt-tab | 4 cards, 18% width, 88% visible, hotkey |
| OBS overlay = always-on chrome spam | Perceptual — opacity = tension, 3 elements max |
| Twitch Extension polls API, guesses | Grounded on VisualContext OCR score/quarter/down |
| Cloud VLM 2s, frame leaves PC | Local ONNX 1.12ms p50 edge, verifiable events_root |
| No provenance | One-tap payload_hash block # — Trio trail |

## Tech (No New Cloud)

- Source: `qoresence/lobes/streamer.py` + `vision/local_vlm.py` + `vision/scoreboard_extractor.py` -> RetinaEventBus (exists).
- New: `qoresence/deck/server.py` ~120L FastAPI + websockets `ws://localhost:8765/retina` `{type:"situation"|"moment", payload:SituationState, score, latency}`. OBS Browser Source = `http://localhost:8765/overlay.html` transparent 60fps canvas.
- Privacy: allowlist `USB3.0 Video` only, MediaPipe BLOCK, `logs/ + .secrets/ + models/ + *.key` gitignored (`6fe965a` ruff . 0).

## Build Order (Exquisite, Not Big Bang)

1. **Week 1 Lens (OBS):** `qoresence/deck/server.py + overlay.html + --play flag`. Ribbon+Pill from live SituationModel. Film Lens not covering ball.
2. **Week 2 Rail (Local):** Tauri drawer + hotkey + Foundry clip -> Helix. Quicksilver whisper.
3. **Week 3 Extension:** Publish Twitch Extension Panel+Overlay mirroring ws via EBS.
4. **Week 4 Ghost+Review:** Scrub + eval histogram.

> Positioning: "Trio for Entertainment Operations — Retina Deck is the first perceptual overlay that proves what it shows." Demo with CLEAN eval 14038 1.0 p50 1.12ms + video of Lens pulsing on 3rd down.

*Hold for "build deck" — no code until approved.*
