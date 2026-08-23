# RETINA DECK — Novel Interoperable Plan (FUTURE)

> **Leftover note:** Twitch Extension / Helix clip language in this plan is not a product route. Local Deck + HDMI Foundry clips are the path.
>
> **Status: FUTURE — Hold until exquisite verified while playing.**
> Do not implement until `logs/session_play_2026-08-06.jsonl` growing + `curl /health ok:true latency ~1.12` + `eye_check FIELD verified` + `ws://8765/retina` pushing live `situation/down` (not mock). See Goose handoff §5.
> Parent specs: `docs/RETINA_DECK_UIUX.md` (Clutch Glass thesis) + `docs/EXQUISITE_PLAN.md` (Play Mode one-command). This doc is the *implementation* plan — interoperable, not 12 bolt-ons.

---

## 1. Purpose & Lane — Own Lane for Gamers Who Stream

**Purpose:** Local opt-in observation layer for gamers who stream. Ingest HDMI `UVC USB3.0 VIDEO idx0 CAP_DSHOW 1280x720@20fps` → build grounded `SituationState` at `1.12ms p50` ONNX edge → drive **ClutchBot** chat/clip/prediction + **Retina Deck** perceptual overlay. No cloud frame egress.

**Lane — what Qoresence is / is not:**

| Is | Is Not |
|---|---|
| Opt-in, local-only `JSONL + ws://127.0.0.1:8765/retina`. Streamer decides what leaves (clip, chat). | Humanity/eligibility, anti-cheat, chain writer |
| `logs/ .secrets/ models/*.onnx *.key` gitignored, `MediaPipe person BLOCK >25%`, `_is_allowed_capture_name` allowlist, `EYE-CHECK logs/eye_check_<ns>.png` human `FIELD verified` | Cloud VLM 2s guess, StreamElements 12-stats covering ball, alt-tab dashboard |
| Equal citizens `ncaa_football_27` + `call_of_duty` via `GameProfileRegistry` — same `SituationModel/MomentScorer/Deck` | Frame leaves PC |
| `Trio for Entertainment Operations` — Sense→Train→Operate→Audit on IoTeX MachineFi. `trio-retina w3bstream_applet.wasm` batch `30s/100` `{payload_hash, events_root merkle, block #}` opt-in provenance | Consensus / eligibility proof |

**Thesis:** `opacity = tension`. Stream stays `92-100%` visible. Deck whispers only when clutch. `Clutch Glass, Not Chrome.` If a feature covers the ball, needs alt-tab, or ships video to cloud, it is out of lane — cut.

---

## 2. Principles (5, enforce lane)

1. **Perceptual, not chrome:** Max `3` elements live, `18%` width cap, `88%` game visible. Motion `spring(0.8s mass 0.9 damping 12)` — ESPN lower-third, not PowerPoint. Respect `prefers-reduced-motion → 0.2s fade`.
2. **Grounded, not guessed:** Every Pill/Spark backed by `FootballScoreboardExtractor 383L bottom-center HUD EasyOCR+regex` + `LocalVLM 3-class [football|unknown|menu] 5-frame 3/5 hysteresis → UNKNOWN 0.38` + `game_profile=ncaa_football_27 guard (shooter→UNKNOWN)`. `!isLive() → Waiting for HDMI…` never mock.
3. **Proven, not asserted:** `Make Clip (last 30s)` → `payload_hash 0x… events_root merkle block #` one tap. Local ONNX latency halo proves edge.
4. **Drawer, not dashboard:** `Ctrl+Shift+R` / `Share+Options` spring drawer. No alt-tab, no second monitor. D-pad navigable, `7:1` over Field `#1A3A2A`.
5. **One brain → N glasses:** `RetinaEventBus (session_id+clock_ns+source_lobe)` single source. Lens (OBS), Rail (local), Viewer (Twitch Extension), Ghost (3s), Review (post-game) are views — no duplicate state.

## 3. Interoperable Architecture — One Brain → Three Glasses + Two Memories

```
[USB3.0 Video idx0] → StreamerRuntime (watchdog 1s, cap.grab retry, fps→15 floor, eye-check 2s)
                    → VisualRuntime 6fps → LocalVLM ONNX 224x224 (p50 1.12) else heuristic 160x90 HSV/Canny/luma
                                   → ScoreboardExtractor (when FOOTBALL) bottom-center → score/quarter/clock/down
                    → SituationModel {home_score,away_score,quarter,down,yards_to_go,possession,field_position}
                       + FootballWinProbability (football-gated) → WP, wp_swing
                       + MomentScorer 777L ClipWorthiness {wp_swing 2.5, red_zone 0.8, close_game 0.6, apm 0.3} 3-6/min
                    ↘
                RetinaEventBus (JSONL, 256 history, ws 8765, trio batch 30s)
              ┌─────┼───────────────────────────┐
              ▼     ▼                           ▼
         ClutchBot  DeckServer(DeckStateV2)  eval/eval_session replay
         Quicksilver deepseek-v4-flash  ws:/retina + /api/*  logs/session_*.jsonl CLEAN 1.0
              │     ├─ A) Lens  OBS 1920×1080 transparent 60fps
              │     ├─ B) Rail  drawer 360px local + hotkey
              │     ├─ C) Viewer Twitch Extension Panel 320px + Video Overlay (EBS)
              │     ├─ D) Ghost  3s memory scrub
              │     └─ E) Review /review histogram
```

**Shared state — `qoresence/deck/server.py` `DeckStateV2` (extends 205L `DeckState`):**

```python
@dataclass class DeckStateV2:
    situation: dict   # SituationState.to_dict() + {win_prob, wp_swing, clip_worthiness, red_zone, close_game}
    last_moment: dict | None
    moments: list[dict]  # append [-100:], snapshot sends [-3:]
---

## 4. Five Interoperable Modules (12 ideas grouped)

### Module 1 — Tension Engine (ideas 1 Tension Glass, 2 Ribbon EKG, 8 Trail live, 9 Halo)

*Inputs:* `clip_worthiness [0,1]` + `wp_swing` + `close_game` + `red_zone` + `latency p50/p95` + `fps`.
*Tension:* `t = clamp(clip*0.9 + wp_swing*1.2 + (red_zone?0.15:0) + (close_game?0.1:0), 0,1)` lerped `0.12/frame` via `requestAnimationFrame` 60fps (<2ms/frame). Fallback CSS `transition 0.8s` if `prefers-reduced-motion`.

| Consumer | Spec |
|---|---|
| **Rail** `deck.html #rail 360px` | `opacity 0.08+t*0.84` `backdrop blur 16-(t*12)px` `border 12%+t*18%`. Boring `t<0.2` ghost, clutch `t>0.75` solid. Game stays `88%` when open. |
| **Ribbon** `#ribbon 1920×4 top:0` | `linear-gradient Field #1A3A2A 0% → Gold #F5C542 pct% (pct=wp*100)` `opacity 0.08+t*0.6`. `wp_swing>0.08` `scaleY 1→2.5 pulse 0.9s`; `Q4<120s & margin≤8` `heartbeat 0.9s infinite`. |
| **Halo/Eye** `#eye right 22 top 16` | `● local 1.12ms p50` `box-shadow 0 0 12px rgba(245,197,66, 0.45*(1-latency/50ms))`. Thumb `eye_check_<ns>.png` 2s preview then `opacity 0` local only. |
| **Trail** `#trail 12px Mono 55%` | Live `● Local ONNX {p50}ms p50 {p95} p95 · 6fps · trio 30s ● block #{n} · CLEAN 1.0` from `bus.stats()` + `LocalVLM.get_stats()` `2s poll /api/situation`. |

### Module 2 — Lens Language (ideas 3 Spark vocab, 6 Sound, 9 Eye proof)

*Source:* `agents/moment_scorer.py` `ClipWorthinessModel` + `SituationState` → `ScoredMoment vocab`.

- **Pill** center `bottom 7% translateX(-50%) frosted rgba(10,14,20,.72) blur12 border chalk 18% radius 999px Mono 13 .04em fade 0.8s in/1.2s out`. `parts join ' · '` = `sc + Q+clock + down&dist + @yl + WP%` max 90 chars. Show only `isLive() && (playclock<15 || down∈{3,4} || t>0.35)`.
- **Spark** vocab queue drop, one at a time, `2.6s` `scale .92→1 spring cubic(.34,1.56,.64,1)` `88px Inter 800 -0.03em Gold glow 32px`: `3rd&2 converted → CHAINS` `4th stop → HOLD` `red zone TD wp_swing>0.15 → HOUSE` `late FG → ICE` `turnover → TAKE` `score_changed → STRIKE`.
- **Sound** optional `tick 80ms -22dB` at `wp_swing>0.15`, `chime 120ms` at `clip>0.75` `<audio volume 0.12 preload>` `mute` toggle in Trail `localStorage deck_mute`. Respects reduced-motion → no sound.
- **Wait** `#wait center 50%` `Retina live — waiting for HDMI Start: python -m qoresence.cli --play` `display none` when `isLive`.


    latency_ms: float    # 1.12 + p95
### Module 3 — Rail Drawer (ideas 4 Drawer spring+hotkey, 7 Foundry proves, 12 Adaptive theme)

*No Tauri Week 1 — pure `deck.html` CSS transform + `keydown` + `Gamepad API 2Hz`.*

- **Drawer:** `position:fixed right:0 top:0 width 360px min-height 100vh transform translateX(100%) → 0 spring 0.8s mass 0.9 damping 12 shadow -16 48 45% backdrop blur 92%`. Hotkey `Ctrl+Shift+R` / `Cmd+Shift+R` + controller `Share+Options hold 400ms` toggles. `Esc` / click outside → `translateX(100%)`. Week 2 wrap same HTML Tauri `globalShortcut`.
- **D-pad:** `Up/Down` cycles 4 cards `tabindex`, `A/Enter` triggers focused card primary, `B` closes. `aria-live polite` Pill.
- **4 cards no scroll while playing, max 18 chars data, Mono 12/14 + Inter 16 Semi:**
  1. Situation Strip 64px `fmt(s)` tap → `ClutchBot enhance_message() TTS whisper Quicksilver 2.6s`.
  2. Clutch Feed 3 max reverse-chrono `00:42 3rd&2 CONVERTED · Clip · Predict` tap clip, long-press prediction (3-6/min cooldown 30/60s).
  3. Foundry `Make Clip (last 30s)` `Gold #F5C542` → `POST /api/clip {window_s:30 at_ns?:clock_ns}` → `HelixClient.create_clip()` + `trio payload_hash/events_root merkle + block_number` → `CLIPPED 00:42 hash 0x… block #28431902`. Failure `queued — twitch delay`.
  4. Trail Dot live (Module 1).
- **Adaptive theme** CSS vars `--ink #0A0E14 --field #1A3A2A --chalk #E8EDF0 --gold #F5C542 --alert #E84C3D` swapped by `category`: `football → Field+Gold`, `shooter → Tactical #1A1A2E + Alert Red`.

### Module 4 — Ghost Replay / Hover Scrub (idea 5 — biggest novel, lane proof)

*No new capture — from `history_3s` ring + `logs/session_*.jsonl` replay + optional `details.thumb b64 160×90`.*

- **Trigger:** `UNKNOWN→FOOTBALL` transition or `clip_worthiness>0.75` → arm `3s scrub bar` under Pill `ticks: 0s Pill 1.5s Spark`.
- **Interaction:** Hover any Feed item → preview layer `408×230 frosted` shows frozen frame from `history_3s` with annotations `Down Pill @0s`, `Spark @1.5s`. Built from ring (18 entries `6fps×3s`) + `eval/eval_session.py` replay. Uses `CouplingAnalyzer 50ms buckets`.
- **Storage tradeoff:** Text+fields first (`score/q/down`), `144KB` (8KB×18) thumbs only if `details.thumb` lands. Push only when `game_category==football && !person` (BLOCK guarantees no room).
- **Why novel:** See *what VLM saw*, not broadcast replay. No extra GPU.

### Module 5 — Viewer Mirror + Review (ideas 11 Viewer, 10 Review)

*Same `ws /retina` + EBS mirror, read-only — no cost to streamer.*

- **Twitch Extension** `tools/twitch-extension/panel.html` `320px Panel` + `Video Overlay 1920×1080` same `ribbon/pill/spark` but `viewer opt-in Retina ON`. `EBS → fetch /api/situation` verified badge `✓ payload_hash` if `trio enabled`.
- **Review** `/deck/review` (post-game when `!isLive`): expand Rail → `canvas histogram p50 1.12 p95 1.98 p99 2.64` + `CLEAN 1.0 precision` badge + searchable Feed `filter: 3rd&2, turnover, red_zone, wp_swing` + `Export JSONL`. Reuse `eval/eval_session.py eval_session(path)` as library for `GET /api/eval?path=logs/latest.jsonl`.

**Interop matrix — every module reads same bus, no duplicate state:**

| Producer → Consumer | `situation` | `moment` | `presence_report/trio` | `eye` | `history_3s` |
|---|---|---|---|---|---|
| Tension Engine | `clip, wp_swing` → t | `weight` | — | — | — |
| Lens Pill/Spark | `sc/q/down/clock/WP` | `title/icon` | — | `verified`→Eye | tick positions |
---

## 5. Data Contracts & APIs (no breaking change to `BaseEvent session_id+clock_ns+source_lobe`)

* `server.py` extends `DeckState→DeckStateV2`, `snapshot()` gains `{trio, eye, history_3s:[-3:]}` — old clients ignore. `FastAPI create_app()` `return None` fallback kept; `stdlib _run_stdlib` mirrors routes.

| Route | Spec | Via |
|---|---|---|
| `GET /health` | `{ok, clients, state: snapshot()}` | existing |
| `GET /api/situation` | `snapshot()` | existing |
| `GET /api/history?n=18` | `DeckState.history_3s` ring | new |
| `GET /api/eval?path=logs/...jsonl` | `eval_session(path)` JSON `{football_precision, shooter_found, avg_vlm_latency_ms, latency_histogram_ms, desync_count, weighted_verdict_counts, passed}` | wraps `eval/eval_session.py` |
| `POST /api/clip {window_s:30 at_ns?:clock_ns}` | `{ok, clip_url?, clip_id?, payload_hash?, events_root?, block_number?, has_delay?}` via `agents/helix_client.py create_clip()` + `trio validator.get_stats()` | new handler |
| `ws /retina` | `type:snapshot|situation|moment` `payload` + `latency_ms` + new `trio/eye/history_3s` | extended `_broadcast` |

* `VisualContext.to_dict()` already `game_category confidence latency_ms model` + football fields — Ghost optional `details.thumb b64`.
* `SituationState.to_dict()` + computed `win_prob, wp_swing, clip_worthiness, red_zone`.
* Security: `DECK_HOST 127.0.0.1` only, `CORS *` stdlib kept, no WS auth Week 1. Tauri Week 2 adds `?token=` check if `QORESENCE_DECK_TOKEN` env.

---

## 6. Stadium Glass Design System (all glasses)

* Palette `Ink #0A0E14 Field #1A3A2A Chalk #E8EDF0 Gold #F5C542 Alert #E84C3D` `12-92%` over video. Contrast `7:1` over field `mean 67.9`.
* Type `JetBrains Mono 12/14 data` `Inter 16 Semi / 88 Bold spark` `max 18 chars/card` while playing.
* Motion `spring 0.8s mass 0.9 damping 12`. Ribbon heartbeat `0.9s` 2-min drill. `prefers-reduced-motion → 0.2s fade` no spring/sound.
* Sound `tick.wav 80ms -22dB` + `chime 120ms` `<audio preload volume 0.12>` mute persists `localStorage deck_mute`.
* A11y D-pad, `tabindex` cards, Pill `aria-live polite`, Spark `role status`.

---

## 7. Build Order — Exquisite, Not Big Bang

| Week | Ship | Files | LoC | Demo |
|---|---|---|---|---|
| **W1 Lens Polish** | Tension `t=f(clip,wp_swing)` + EKG + Spark vocab queue + Eye 2s + tick + halo + Trail live | `deck/server.py + DeckStateV2 + /api/eval + POST /api/clip stub + history_3s ring` `deck/overlay.html rAF lerp + pulseY` `deck/deck.html tension blur + Trail poll 2s` `cli.py history push + latency p50/p95` `agents/moment_scorer.py SPARK_VOCAB` | ~120 server +60 overlay +40 rail | Film Lens not covering ball but pulsing `CHAINS` on 3rd&2 |
| **W2 Rail Drawer** | Spring drawer `transform 100%→0` + `Ctrl+Shift+R` + `Gamepad 2Hz` + `Esc/outside` + D-pad + `88% game` + Foundry real Helix when creds | `deck/deck.html transform spring + keydown/Gamepad + focus mgr` `deck/server.py POST /api/clip real HelixClient` `agents/clutchbot.py enhance_message TTS` | ~80 rail +40 server | Call Rail while playing, clip without alt-tab |
| **W3 Extension** | Publish Twitch Extension Panel 320px + Video Overlay mirroring `ws/EBS` readonly verified badge | `tools/twitch-extension/panel.html + overlay` (same `handle()` read-only) `EBS` config | ~100 panel | Viewer clicks Retina ON sees your Pill, no cost to you |
| **W4 Ghost+Review** | `3s scrub bar` + hover preview `408×230` + `/deck/review` histogram `p50/p95/p99` + `CLEAN 1.0` + searchable feed + Export JSONL | `deck/server.py /api/history` `deck/deck.html+overlay.html scrub` `deck/review.html canvas` `eval/eval_session.py library` | ~90 server+html | Post-game proof: what VLM saw + `p50 1.12` |

*Cross-cutting every week:* `ruff check .` + `ruff format --check` `0`, `mypy --strict disallow_untyped_defs`, `pytest 287` + `eval/eval_session.py CLEAN → football_precision 1.0 p50<100ms` in `ci.yml`.

---
## 8. Why Novel vs Existing (lane proof)

| Existing | Retina Deck (this plan) |
|---|---|
| StreamElements 12 stats covering ball, alt-tab | 4 cards 18% width 88% visible drawer hotkey D-pad |
| OBS overlay always chrome spam | Perceptual `t=f(clip,wp_swing)` tension glass 3 elements max `0` when boring |
| Cloud VLM 2s frame leaves PC | Local ONNX `1.12ms` edge `person BLOCK` OCR grounded `score/q/down` |
| Twitch poll API guesses | WS `RetinaEventBus session_id+clock_ns` ordered `isLive()` grounded |
| No provenance | `payload_hash events_root block #` one tap via Trio — proves what it shows |
| No replay | `3s Ghost` from local JSONL — see what VLM saw, no extra capture |
| Post-game scattered logs | `/review` histogram `p50/p95/p99` + `CLEAN 1.0` + search |

> Positioning: `Trio for Entertainment Operations — Retina Deck is the first perceptual overlay that proves what it shows. Demo with CLEAN eval 14038 1.0 p50 1.12ms + video of Lens pulsing on 3rd down.`

---


## 9. Verification (done = not mocked)

* **Visual:** `football_precision 1.0 shooter_found 0` on `logs/session_2026-08-06_direct_usb0_CLEAN.jsonl 14038 ev 9.09MB`, `avg <100ms p50~1.12 p95~1.98` via `eval/eval_session.py`.
* **Streamer:** `5 min direct capture 0 temporal_desync`, watchdog `1s heartbeat` (fix `c953d04`).
* **Deck:** `python -m qoresence.cli --play` → `http://127.0.0.1:8765/{health,api/situation,deck.html,overlay.html}` WS connected, `Waiting → LIVE` when `score/q/down` populates, `ribbon opacity=f(t)`, `3 moments max`, `Foundry POST /api/clip → hash block`.
* **A11y/perf:** `rAF 60fps <2ms/frame`, `7:1` contrast, `prefers-reduced-motion` path.
* **Privacy:** `git ls-files *.png|jpg` empty, `git check-ignore -v logs/` , device allowlist untouched.
* **Tests:** new `tests/test_deck_v2.py` `{snapshot shape, history ring 18, clip mock, tension clamp, theme vars, rAF lerp}`.

---

## 10. Alternatives Rejected & Tradeoffs

| Alternative | Rejected because |
|---|---|
| New WS per glass | One `ws /retina` + `poll 2s` fallback resilient; multi-WS duplicates `DeckState`. Keep one. |
| Tauri hotkey day one | Adds Rust toolchain, breaks `stdlib fallback Local only`. Pure HTML `keydown/Gamepad` first, wrap Week 2. |
| Store thumbs day one | `b64 144KB` ring needs privacy review. Start text+fields, add thumb when `details.thumb` lands. |
| Cloud clip buffer / S3 | Violates `frame never leaves PC`. Use `history_3s` ring + `Helix` + `payload_hash` local proof. |
| Auth on WS now | Loopback `127.0.0.1` proof enough; add `?token=` only when Tauri→EBS exposes beyond loopback. |
| New WS port for Deck | Keep `8765` shared; if busy `EADDRINUSE try port+1 + log QORESENCE_DECK_PORT env`. |
| Rewrite `RetinaEventBus` WS | Keep shared port `QORESENCE_WS_PORT vs QORESENCE_DECK_PORT` env, do not duplicate. |

---

## 11. Risks & Mitigations

* **CRLF churn (`cli.py BOM`, `visual.py game_profile=None`)** — `git diff HEAD 86/54` lint only. Normalize `git add --renormalize .` → `chore: normalize LF` before Deck V2.
* **Port clash `bus ws 8765` vs `deck 8765`** — `start_deck try/except OSError -> log Deck on {port+1} + DECK_PORT env`.
* **Replay thumb privacy** — Ghost never stores room frame (BLOCK). Audit `history_3s` push only `game_category==football && !person`.
* **Helix clip delay** — `ClutchBotConfig clip_has_delay True` — Foundry shows `queued` not `failed`.
* **Scoreboard blocking** — `EasyOCR 383L` lazy-load after warmup; Week 1 `QORESENCE_SCOREBOARD_ENABLED=0` recovers `1.12ms`, Week 4 re-enable lazily.
* **Sound:** `prefers-reduced-motion` and `deck_mute` gate; default muted until user taps `Sound ON`.
---

## 12. Goose Handoff Link — How This Plan Depends On Live Verification

Goose handoff `Sense→Train→Operate→Audit + Deck 54ac720 fd90cca` is accurate. Blockers `401 Nvidia → force prefer_local`, `game_profile TypeError → patch 22L`, `10048 stale 7672 → taskkill`, `EasyOCR blocking → SCOREBOARD_ENABLED=0` are correct interim fixes. This novel plan **depends on** Goose §5 `5-checks` passing before any W1 code:

```
logs/eye_check*.png newest >500KB green>0.06 FIELD
logs/session_play_2026-08-06.jsonl lines>0 growing
curl http://127.0.0.1:8765/health ok:true latency ~1.12
ws://8765/retina pushes situation/down not mock
py_compile + ruff 0 → commit fix(visual+deck): live HDMI ONNX fallback + Bus->deck bridge verify → push 0-ahead
```

Do not create `NOVELTY.md` or update `docs/ARCHITECTURE.md` diagram until exquisite verified while playing (user explicit). This `RETINA_DECK_NOVEL_PLAN.md` is `FUTURE` — hold, not implement.

### Handoff batch for next play session (approved B does NOT run — save for when HDMI live):

```powershell
# 1. kill stale deck + verify
netstat -ano | findstr 8765 ; taskkill /F /PID 7672 2>nul
python -m py_compile qoresence/lobes/visual.py qoresence/cli.py qoresence/deck/server.py
if ($LASTEXITCODE -eq 0) { echo PY_OK } else { echo PY_FAIL }
python -m ruff check qoresence/deck qoresence/cli qoresence/vision/local_vlm --quiet; if ($LASTEXITCODE -eq 0) { echo RUFF_OK }

# 2. relaunch play daemon (prefer_local + no scoreboard) — explicit jsonl
$env:QORESENCE_VISUAL_PREFER_LOCAL=1; $env:QORESENCE_VISUAL_LOCAL_FALLBACK=1; $env:QORESENCE_SCOREBOARD_ENABLED=0; $env:QORESENCE_DECK_ENABLED=1; $env:QORESENCE_CLUTCHBOT_LLM_ENABLED=1
Start-Process python -ArgumentList "-m qoresence.cli --play --log-level INFO --jsonl-path logs/session_play_2026-08-06.jsonl" -RedirectStandardOutput logs/capture.out -RedirectStandardError logs/capture.err -WindowStyle Hidden
Start-Sleep 8; Get-Content logs/capture.err -Tail 40
Get-ChildItem logs/eye_check*.png | Sort LastWriteTime | Select -Last 1 | Format-List Length,LastWriteTime
if (Test-Path logs/session_play_2026-08-06.jsonl){ (Get-Content logs/session_play_2026-08-06.jsonl | Measure-Object -Line).Lines } else { echo JSONL_MISSING }
try{ Invoke-RestMethod http://127.0.0.1:8765/health | ConvertTo-Json -Depth 3 } catch{ echo HEALTH_FAIL $_ }

# 3. if PY_OK + RUFF_OK + JSONL>0 + health ok -> commit/push
# git add qoresence/lobes/visual.py qoresence/cli.py qoresence/deck/overlay.html qoresence/deck/deck.html
# git commit -m "fix(visual+deck): live HDMI ONNX fallback + Bus->deck bridge verify"
# git push
```

**Key files:** `qoresence/vision/local_vlm.py:117` heuristic, `qoresence/lobes/visual.py:483` `game_profile` call, `qoresence/cli.py:323 --play` parser + `350` wiring, `qoresence/deck/server.py:205 DeckState`, `.secrets/quicksilver_clutchbot.key` (25B gitignored), `logs/capture.out/err`, `eval/eval_session.py`.

---

*Hold for `verify exquisite while playing` — no code until approved. Then W1 Lens Polish pure `server.py + overlay.html + deck.html` patch, `ruff 0`, `pytest 287`.*

*Generated 2026-08-06 — Goose handoff + Cline lane plan → future doc `docs/RETINA_DECK_NOVEL_PLAN.md`.*
