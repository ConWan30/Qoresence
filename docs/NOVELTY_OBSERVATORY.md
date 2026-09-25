# Local-First Gaming Streaming Observatory — Novelty Research
Operator canon for the 2026-09-05 ranking. First shipping slice: Null Digit + Ticket Freshness → Lease/Spout → Integrity Board → Coupling Meter.
Date: 2026-09-05 (America/Chicago)  
Scope: competitive gaps + ranked novelty candidates under hard purpose constraints.  
Not reinvented: FrameHub, IVC, Ghost Stick, ticket-clock, Dark Theater / Aperture Ident, Spout Glass spike, Session Theater, CIVIF, Foundry RAG, Quicksilver VLM scorebug, Pattern B OBS recipe, Live 0.9.0 docs.

---

## 1. Competitive gaps (what they do NOT own)

| Adjacent class | Examples | What they optimize | Gap this purpose owns |
|---|---|---|---|
| Stream platforms | Twitch, Kick, YouTube Live, X Live Studio | Audience, chat, discovery, RTMP ingest | No capture-card brain; no HID↔HDMI monotonic join; no fail-closed observation plane; X Live Studio is destination glass only ([X Live Studio](https://quasa.io/media/x-launches-live-studio-to-simplify-livestream-broadcasting), [Streamlabs X RTMP](https://streamlabs.com/content-hub/post/how-to-live-stream-to-twitter)) |
| Operator-authored scorebugs | [Fly Scoreboard](https://github.com/mmlTools/fly-scoreboard/), [tally-scorebug](https://github.com/FlashGalatine/tally-scorebug), [html-score](https://github.com/bakedpanda/html-score), [Streamn Scoreboard](https://github.com/StreamnDad/streamn-scoreboard) | Hotkeys / Stream Deck / chat bump scores | Digits are human-authored truth; no ConfirmTicket + VLM lock; no blank-on-stale |
| OCR score pipelines | [Scoreboard OCR FAQ](https://scoreboard-ocr.com/faq), [HTML Scorebug + OCR](https://obsproject.com/forum/resources/html-scorebug-with-ocr-support-manual-control-dashboard-and-automated-ticker.2293/) | Keep last-good when digits vanish (`Ignore Empty values`) | **Opposite of fail-closed** — last-good freeze is the product feature |
| Cloud sports overlays | [StreamSlayers scorebug](https://streamslayers.com/blog/how-to-add-a-scorebug-overlay-to-obs) | League feeds + delay slider | Not local-first; not capture-card-subscribed; invents continuity from remote feed |
| Game OCR / live HUD scrapers | [Live-Valorant-Overlay](https://github.com/deepsidh9/Live-Valorant-Overlay), [valoscribe](https://github.com/SphinxNumberNine/valoscribe) | Template+OCR → overlay JSON | Invent/guess when confidence low; no ticket-fresh gate; often dual-capture |
| AI stream directors | [Stream-Mind](https://github.com/Stream-Mind/Stream-Mind), [AMD AI director](https://github.com/munhim2005/AMD-Hackathon) | Auto scene switch, chat gen, “boss fight” labels | Authorship / show-running plane — not observation |
| Highlight / clutch AI | [stream-clipper](https://github.com/nirvagold/stream-clipper), ClipStudio-style LLaVA scorers | “Best moments”, clip authorship | Claims significance / highlight worth — authorship-law risk |
| Controller overlays | [Gamepad Viewer](https://gpadtester.net/gamepad-viewer/), [PS5 visualizer](https://github.com/8bitdev0x8/ps5-controller-visualizer) | Browser Gamepad API pretty stick | No `clock_ns`/`frame_seq` join to HDMI; can fight DualSense exclusivity; display ≠ evidence |
| Capture latency discourse | [RetroRGB capture latency](https://retrorgb.com/understanding-capture-card-input-latency.html), [Elgato passthrough](https://www.elgato.com/us/en/explorer/products/capture/passthrough-vs-capture-whats-the-difference-on-a-capture-card/) | Passthrough vs preview lag | Explains play lag; does not publish pad↔picture coupling evidence |
| Spout / local GPU glass | [Off-World Spout2](https://knowledge.offworld.live/articles/5059810-spout-plugin-for-obs-studio) | Zero-copy local preview | Glass transport only — no observatory semantics, tickets, or fail-closed widgets |
| Evidence-grade multi-sensor sync | [CHRONYX-CORE](https://github.com/Sherin-SEF-AI/CHRONYX-CORE), [Evidence-grade telemetry](https://dev.to/applekoiot/evidence-grade-telemetry-sensor-sync-time-bases-and-idempotent-ingestion-2g15) | Monotonic join of camera+IMU+audio | Adjacent *method*; not shipped as gaming stream observatory |

**Owned white space (one sentence):** a local observatory where the capture card is sole DShow owner, glasses subscribe, HDMI + DualSense + situation share one monotonic clock, digits appear only under ticket+lock+fresh, and widgets go blank/Ident/dark rather than freeze last-good or invent.

---

## 2–3. Ranked novelty candidates (20)

Ranking axes (higher = better fit): **(1) lag/freeze↓ (2) honest scorebug (3) pad↔picture sync (4) clutch w/o authorship (5) Deck delight**. Scores 1–5 each; total /25.

### Rank 1 — **Null Digit Glass** (total 23)
- **Lobe/glass:** `NullDigitGlass` (glass) + `DigitIntegrityLobe` (lobe, default OFF)
- **Trigger:** ticket missing / `score_vlm_locked=false` / ticket stale / path=`fast` / VLM abstain
- **Veto:** any path that would paint last-good digits; any auto-fill from Foundry RAG
- **Ship size:** PR (wire to Quicksilver + Dark Theater Ident already in flight)
- **Authorship risk:** **None** — blank/Ident is anti-authorship
- **Why novel:** industry default is ScoreboardOCR “Ignore Empty → keep old” ([FAQ](https://scoreboard-ocr.com/faq)); you ship the inverse as product law
- **Axes:** 5 / 5 / 3 / 4 / 4

### Rank 2 — **Single-Open Lease** (total 22)
- **Lobe/glass:** `CaptureLeaseLobe` + `LeaseBadge` on Deck
- **Trigger:** session start; any second process attempting DShow/MediaFoundation open on same device
- **Veto:** dual-open; “preview in app + OBS capture” recipes; soft-share
- **Ship size:** spike → PR (watchdog + named mutex/lease file + Deck kill switch)
- **Authorship risk:** None
- **Why novel:** Twitch tutorials still dual-open; Spout/NDI docs never police DShow exclusivity as observatory law
- **Axes:** 5 / 3 / 4 / 3 / 5

### Rank 3 — **Coupling Meter Glass** (total 22)
- **Lobe/glass:** `CouplingMeterGlass` (pad event ↔ frame_seq Δ)
- **Trigger:** DualSense report joined to nearest `frame_seq` within window; show lag histogram + skew
- **Veto:** labels like “cheating”, “lag switch”, “human reaction”; thresholds as eligibility
- **Ship size:** PR (Ghost Stick + FrameHub clock already exist)
- **Authorship risk:** Low if UI says “coupling / co-occurrence only”
- **Why novel:** Gamepad viewers show pretty pads; capture blogs show passthrough ms; nobody ships **joined evidence** of pad↔picture on one clock ([Gamepad Viewer](https://gpadtester.net/gamepad-viewer/), [CHRONYX pattern](https://github.com/Sherin-SEF-AI/CHRONYX-CORE))
- **Axes:** 4 / 2 / 5 / 4 / 5

### Rank 4 — **Ticket Freshness Strip** (total 21)
- **Lobe/glass:** `TicketFreshStrip` on scorebug chrome
- **Trigger:** ConfirmTicket age > N frames or clock_ns drift → digits → blank; strip turns amber→red→Ident
- **Veto:** path=`fast` painting digits; soft “stale but visible”
- **Ship size:** PR
- **Authorship risk:** None
- **Why novel:** Stream delay sliders keep wrong digits in sync with picture ([StreamSlayers](https://streamslayers.com/blog/how-to-add-a-scorebug-overlay-to-obs)); you expire digits
- **Axes:** 4 / 5 / 2 / 3 / 5

### Rank 5 — **Presence Lattice** (total 21)
- **Lobe/glass:** `PresenceLatticeLobe` → `LatticeGlass`
- **Trigger:** co-occurrence of (button chord class × HUD ROI change × audio onset) inside ±K frames — emit **presence tokens**, not “clutch”
- **Veto:** ranking, highlight export, “best play”, eligibility scores
- **Ship size:** phase (needs CIVIF + Ghost Stick + FrameHub)
- **Authorship risk:** **Medium** if UI drifts to highlight language — keep vocabulary: presence / co-occurrence / density
- **Axes:** 3 / 2 / 5 / 5 / 4

### Rank 6 — **Skew Alarm Deck Tile** (total 20)
- **Lobe/glass:** Deck tile `SkewAlarm` (operator only; not on program glass by default)
- **Trigger:** `|clock_ns_hid − clock_ns_hdmi|` or frame_seq gap exceeds budget; freeze risk predicted
- **Veto:** auto “fix” that invents interpolated HID; auto scene cut that claims drama
- **Ship size:** spike
- **Authorship risk:** None (ops signal)
- **Axes:** 5 / 2 / 5 / 2 / 5

### Rank 7 — **Dark Failover Cascade** (total 20)
- **Lobe/glass:** `FailCascade` policy (widget → dark → Aperture Ident → program hold)
- **Trigger:** Spout sender gone, browser source hung, ticket expired, VLM timeout
- **Veto:** last-frame freeze of scorebug or stick glass; synthetic hold of digits
- **Ship size:** PR (extends Dark Theater / Ident)
- **Authorship risk:** None
- **Why novel:** OBS browser freeze is a known failure mode ([obs#12796](https://github.com/obsproject/obs-studio/issues/12796)); cascade is productized honesty
- **Axes:** 5 / 5 / 2 / 3 / 4

### Rank 8 — **Subscribe-Only Spout Contract** (total 19)
- **Lobe/glass:** `GlassSubscribeSpec` (FrameHub Spout out; OBS Spout2 Capture only)
- **Trigger:** Pattern B session; glasses register as subscribers with lease id
- **Veto:** second DShow Video Capture Device on same card; NDI pull that re-opens device
- **Ship size:** PR (Spout Glass spike exists — harden as contract + docs + Deck health)
- **Authorship risk:** None
- **Axes:** 5 / 2 / 3 / 2 / 5

### Rank 9 — **Abstain Quicksilver Path** (total 19)
- **Lobe/glass:** Quicksilver mode `path=confirm` only for digits; `path=fast` = geometry/Ident only
- **Trigger:** every digit paint requires ConfirmTicket + `score_vlm_locked` + ticket-fresh
- **Veto:** OCR fallback invent; RAG “likely score”; majority vote without lock
- **Ship size:** PR
- **Authorship risk:** Low (explicit abstain)
- **Why novel:** Valorant OCR overlays and sports OCR chase continuity; you chase **abstention**
- **Axes:** 3 / 5 / 1 / 4 / 4

### Rank 10 — **Ghost Stick Phase Glass** (total 19)
- **Lobe/glass:** `PhaseGhostGlass` — stick trail as phase portrait vs frame_seq, not decorative skin
- **Trigger:** session with HID join; optional lobe ON
- **Veto:** “skill rating”, “input fairness”, anti-cheat language
- **Ship size:** spike (extends Ghost Stick)
- **Authorship risk:** Low→Med if marketed as skill viz
- **Axes:** 3 / 1 / 5 / 4 / 4

### Rank 11 — **Situation Bookmark (no claim)** (total 18)
- **Lobe/glass:** `BookmarkLobe` — operator or presence-token drops `frame_seq` bookmark; no title semantics
- **Trigger:** Deck hit / presence density peak (if Presence Lattice ON)
- **Veto:** auto title “CLUTCH”; auto upload as highlight reel with evaluative copy
- **Ship size:** spike → PR
- **Authorship risk:** Medium unless bookmarks stay unlabeled evidence pointers
- **Axes:** 2 / 1 / 3 / 5 / 5

### Rank 12 — **X Pixel Glass Only** (total 18)
- **Lobe/glass:** `XPixelGlass` — OBS RTMP program out; **X Glass receipts default OFF**
- **Trigger:** go-live to X Live Studio ingest
- **Veto:** shipping coupling meters / tickets / HID evidence to public by default
- **Ship size:** PR (docs + Deck toggle “receipts OFF”)
- **Authorship risk:** Low if public = pixels only
- **Cite:** [X Live Studio](https://gigazine.net/gsc_news/en/20260703-x-live-studio/), [Streamlabs X](https://streamlabs.com/content-hub/post/how-to-live-stream-to-twitter)
- **Axes:** 4 / 3 / 2 / 3 / 4

### Rank 13 — **Receipt Drawer (opt-in)** (total 17)
- **Lobe/glass:** `ReceiptDrawer` — local JSONL of (frame_seq, ticket id, digit state, coupling bins); export gated
- **Trigger:** lobe ON; session end or Deck export
- **Veto:** public auto-post; “proof you are human”; eligibility attestation
- **Ship size:** phase
- **Authorship risk:** Medium — receipts can be misread as anti-cheat dossiers; default OFF + observation vocabulary mandatory
- **Axes:** 2 / 4 / 4 / 4 / 3

### Rank 14 — **Freeze Prophet** (total 17)
- **Lobe/glass:** `FreezeProphetLobe` — predict browser/Spout stall from heartbeat misses; pre-emptive Ident
- **Trigger:** glass heartbeat gap; CEF GPU crash patterns
- **Veto:** “recover” by replaying buffered last digits
- **Ship size:** spike
- **Authorship risk:** None
- **Axes:** 5 / 4 / 1 / 2 / 3

### Rank 15 — **Deck Integrity Board** (total 17)
- **Lobe/glass:** Stream Deck / virtual Deck profile `IntegrityBoard`
- **Tiles:** Lease OK · Ticket age · Digit path · Spout subscribers · Skew · Lobe master OFF · Ident now · Blank digits
- **Trigger:** always on operator surface
- **Veto:** tiles that bump scores (that’s Fly/tally territory)
- **Ship size:** PR
- **Authorship risk:** None
- **Why novel:** existing Deck plugins are score *bumpers* ([KeepTheScore](https://keepthescore.com/docs/streamdeck-integration/), [overlays.uno](https://resources.overlays.uno/post/stream-deck-control-panels-for-sport)); yours is integrity *instrumentation*
- **Axes:** 3 / 4 / 3 / 2 / 5

### Rank 16 — **Co-Occurrence Heatmap (session theater)** (total 16)
- **Lobe/glass:** `CoHeatGlass` inside Session Theater — density over time, not ranked plays
- **Trigger:** lobe ON after session or live low-res
- **Veto:** top-10 clutch list; sharecard with evaluative adjectives
- **Ship size:** phase
- **Authorship risk:** Medium (visual rhetoric can imply authorship)
- **Axes:** 2 / 1 / 4 / 5 / 3

### Rank 17 — **Ident-as-Product Chroming** (total 16)
- **Lobe/glass:** branded Aperture Ident variants for digit-void / lease-loss / skew-trip (still fail-closed)
- **Trigger:** same as Null Digit / Fail Cascade
- **Veto:** Ident that shows guessed score “for continuity”
- **Ship size:** spike (design) → PR
- **Authorship risk:** None
- **Axes:** 3 / 5 / 1 / 2 / 4

### Rank 18 — **HID Exclusive Affinity** (total 16)
- **Lobe/glass:** `HidAffinityLobe` — sole DualSense reader under FrameHub; glasses get reports via bus, not second HID open
- **Trigger:** pad connect
- **Veto:** browser Gamepad API overlay + native HID both open (common OBS recipe)
- **Ship size:** PR
- **Authorship risk:** None
- **Axes:** 4 / 1 / 5 / 2 / 3

### Rank 19 — **Situation Bus (observation topics)** (total 15)
- **Lobe/glass:** `SituationBus` topics: `presence.*`, `coupling.*`, `digit.state`, `lease.*` — never `author.*`, `eligible.*`, `human.*`
- **Trigger:** always under FrameHub
- **Veto:** topic names that imply judgment
- **Ship size:** phase (schema + CIVIF alignment)
- **Authorship risk:** Low if schema police holds
- **Axes:** 3 / 3 / 3 / 4 / 2

### Rank 20 — **Public Pixel Delay Match** (total 14)
- **Lobe/glass:** `EgressDelayGlass` — match OBS RTMP buffer to ticket freshness window so public never sees digits the local plane already blanked
- **Trigger:** X/Twitch egress
- **Veto:** delay that *reintroduces* expired digits from buffer
- **Ship size:** spike
- **Authorship risk:** None
- **Axes:** 4 / 5 / 1 / 1 / 2

---

## Honorable near-misses (do not rank as new product if they collapse into existing)

| Name | Why near-miss |
|---|---|
| Quicksilver Confirm UI polish | Already in flight as Quicksilver VLM scorebug |
| Spout Glass health LED | Belongs under Subscribe-Only Spout Contract / Integrity Board |
| Session Theater timeline scrub | Exists; only add CoHeat if observation-only |
| Ghost Stick cosmetic skins | Exists; Phase Glass is the novel bit |

---

## 4. Explicit non-ideas

| Non-idea | Why banned |
|---|---|
| **Second brain / AI director** that switches scenes, writes chat, “runs the show” | Authorship plane ([Stream-Mind](https://github.com/Stream-Mind/Stream-Mind), AMD director) |
| **Truth plane** (“true score”, “true clutch”, “proved human”) | Outside observation; invents adjudication |
| **Dual-open DShow** (OBS + app both open capture) | Breaks capture-card-as-brain; lease conflict |
| **Inventing / last-good scores** when OCR/VLM blank | Industry default ([Scoreboard OCR Ignore Empty](https://scoreboard-ocr.com/faq)); violates fail-closed + ticket law |
| **path=fast digit paint** | Hard veto |
| **Anti-cheat / eligibility / humanity attestations** from coupling | Observation ≠ enforcement |
| **Highlight reels with evaluative titles** auto-published | Clutch-as-authorship |
| **X Glass receipts default ON** | Hard constraint: default OFF |
| **Lobes default ON** | Hard constraint: opt-in OFF |
| **Browser Gamepad overlay as evidence** without FrameHub clock join | Pretty ≠ joined |
| **Cloud league scorebug as local truth** | Not local-first; continuity theater |
| **Reinvent FrameHub / IVC / Ghost Stick / ticket-clock / Dark Theater / Spout Glass / Session Theater / CIVIF / Foundry RAG / Quicksilver / Pattern B** as “new” | Already exists or in flight |

---

## Suggested first shipping slice (concrete, not vapor)

0. **SEQGATE v0** — named frame-license harness over Null Digit + ticket-fresh + capture lease. See [SEQGATE.md](SEQGATE.md). Ident Latch (#145) stays HOLD. Integrity Board tiles stay empty (HOLD note). Memory is a third glass: [SEQGATE-Memory-Wiring.md](SEQGATE-Memory-Wiring.md).
1. **Null Digit Glass + Ticket Freshness Strip** (honest scorebug law visible on program)  
2. **Single-Open Lease + Subscribe-Only Spout Contract** (lag/freeze↓ + dual-open death)  
3. **Deck Integrity Board + Skew Alarm** (operator delight without score bumping)  
4. **Coupling Meter Glass** (pad↔picture sync as presence evidence)  
5. Keep **Presence Lattice / Bookmarks / Receipts** behind default-OFF lobes with vocabulary lint

---

## TypeSafe Noul observatory (shipped, default OFF)

`--noul` / `QORESENCE_NOUL=1` adds an observation-plane worker that asks Jev (or a local heuristic) whether a VLM parse looks like a **live scorebug**, **true pause**, or **clip-worthy presence**. Composition lives in code. **Noul never licenses digits** (`licenses_digits: false`). Same enqueue-only contract as OTel. `--play` does not enable it. Extra: `pip install qoresence[noul]` + `TYPESAFE_API_KEY`.

### Honesty Lattice (operator Integrity Board)

Composite of TypeSafe **Score** dimensions, weights in code (`HONESTY_WEIGHTS`):

| Dimension | Primitive | Role |
| --- | --- | --- |
| `board_honesty` | Score 0–2 | Inverse of last-good OCR freeze |
| `presence_density` | Score 0–2 | Pad↔picture join — tokens `idle` / `join` / `dense` (not clutch) |
| `last_good_temptation` | Noul | Would industry paint stale digits? High → Ident |

Deck Integrity Board (operator-only, never Lens) shows Honesty / Presence / HUD tiles when noul is on. Changing a weight does not require a new inference.

### Clip segments (Situation Bookmark, no claim)

While noul is on, the observatory keeps a bounded run-length history of `(hud_kind, presence_token, confidence bucket, true_pause bucket)`, plus a bounded ring of slim VLM snapshots (clock, quarter, teams present, `paused_raw`, prompt; no digits). Both are appended under the observatory's own lock, and nothing is emitted. At clip export, `clip_chapters.build_segments_for_window` turns the history into a `segments` list on `<name>.chapters.json`: Live / Pre-play / Play select / Paused / Menu / Loading / No board, plus idle / join / dense. The Deck uses it for seek and an opt-in "Skip pauses/menus/loading". This is structure, not highlights: closed vocabulary, `licenses_digits: false`, and no segments when noul is off. See [STEM.md](STEM.md#segments-chapters-sidecar).

`pause` is an in-game pause overlay (the scorebug may still show); `select_plate` stays the SELECT plate that invents a score pair. The VLM's own pause read is kept as `paused_raw` before `normalize_vlm_paused_flag` clears `paused` for digit honesty. Because the VLM also false-positives `paused` on live HUDs, a raw-only pause is a low-confidence `pause` that cannot auto-cut.

### Clip excision (Cut Receipt, default OFF)

`--clip-excise` / `QORESENCE_CLIP_EXCISE=1`. After an HDMI clip is written, `qoresence/vision/clip_excise.py` finds candidate dead spans (pause / select_plate / menu / loading segments and frozen-picture runs) and decides cut / suggest / keep per span. The original `<stem>.mp4` is never modified; the edit is `<stem>.cut.mp4` plus a `<stem>.cut.json` receipt with each span's evidence, answers, decision, reason, the Jev model version, `policy_version`, and a `time_map` back to source time.

- **Span Referee:** with `--noul` or `--jev` and a key, one Jev request per clip (pinned `jev-1.13.0`, override `QORESENCE_EXCISE_MODEL`) asks three fan-out questions per span: what was on screen (with `unknown`), was gameplay suspended and resumed from the same moment, and would removing it hide live play.
- **Triple Proof (offline):** without the referee, only pauses with `paused_raw` throughout + ≥1.5 s frozen picture + (unchanged game clock or an Options press) are cut. The game-clock leg only counts when the operator has pinned a football profile (`QORESENCE_GAME_PROFILE` or the last pin, recorded as `game_profile` in the receipt); other or unknown titles need the Options press. Menus and loading are never cut offline.
- **Fail closed:** spans with a ticket or chapter mark inside, `hides_play ≥ 0.3`, `unknown` / `gameplay`, or confidence < 0.6 are kept. 0.6–0.85 becomes a Deck suggestion (kept until the gamer accepts). Replays and cutscenes are suggest-only. 0.4 s is kept on each side of a cut, and a plan that would remove more than 60 % of the clip keeps everything.
- The referee and ffmpeg render run on a bounded `clip-excise` worker: no bus events, no lobe locks, nothing on the capture thread. The Deck shows an Edited / Original toggle and a per-span receipt with Cut / Keep; overrides re-render from the original and are appended to `excise_labels.jsonl` in the clip folder (policy decision vs gamer decision, bounded at 5 MB) as labelled pilot evidence.

#### Pilot gate (before any default change)

**Labelling on the Theater.** While a clip replays, the Cut receipt card (floating top-right on the home Theater, `glass/src/components/theater/replay-cut-panel.tsx`) has **Label this clip**. Labelling is blind: it switches to the original picture and hides the receipt strip and spans. Mark start → End · Pause / Menu / Loading → Save labels. Labels go to `clips/excise_ground_truth.json` through loopback-only `POST /api/excise/labels/{stem}` (the game profile is copied from the receipt). The card's last line shows `GET /api/excise/gate` progress. The classic `deck.html` fallback has the same card.

`scripts/excise_pilot_gate.py` scores receipts against hand labels and never changes a default. It reads the Theater labels by default:

```bash
python scripts/excise_pilot_gate.py --clips clips --health logs/pilot/*.json          # Theater labels
python scripts/excise_pilot_gate.py --clips clips --init-labels labels.json          # or hand-edit JSON
python scripts/excise_pilot_gate.py --clips clips --labels labels.json --health logs/pilot/*.json
```

**Health evidence is automatic.** While each excision job runs (referee + ffmpeg render), the worker samples live `age_s` from the FrameHub stamp every 0.5 s (the same read `/health` uses) and records `health: {samples, no_frame, age_s_max, age_s_p50, jobs}` in the receipt, keeping the worst value across re-renders. The gate counts these alongside any `--health` snapshot files. `python scripts/pilot_preflight.py` now prints soft excision checks: ffmpeg, clips folder, pinned football profile, `--clip-excise`, TypeSafe key present (never printed), and gate progress.

It scores the policy's own cuts (gamer overrides stripped). `fail` (exit 1): any cut removes labelled live play (over-cut must be 0), any Deck veto of an auto-cut, `/health` `age_s` ≥ 1.0 s in the supplied snapshots, or Jev receipts from a model other than the pin. `insufficient` (exit 2): fewer than 20 football clips with labelled dead spans, no labelled pause, menu or loading, labelled clips without receipts, or no `/health` samples. `pass` (exit 0) otherwise. Under-cut and the suggest-accept rate are reported, not gated. The report is written to `logs/pilot/excise_gate_<ts>.json`.

### Jev conductor (ClutchBot / MatchAgent *text*, default OFF)

`--jev` / `QORESENCE_JEV=1`. Jev is **text-only** — it cannot see HDMI. Pixel harvest stays on the VLM. The conductor **selects** closed templates (Choice + speculative Noul clip/arm) instead of generating chat. Code fills digits from the confirm ticket only. Key: `TYPESAFE_API_KEY` or `.secrets/typesafe.key` (never commit). `--play` does not enable.

Gamer product (Theater / Session Now, never Lens): HonestyLine — “Would rather go blank than keep a stale score” + presence `idle/join/dense`. Recap export runs hygiene; HOLD on digit leak / truth dest — never a QorTroller seal.

### Jev press labeler (laptop-HID presses, same `--jev` flag)

Deterministic EA sheets already label `button + mode → verb`. When `mode` is None (ambiguous picture sheet) or a sheet conflict fires, every press goes **unlabeled** — the labeler is the referee for that gap. Three outcomes, fail-closed: `labeled` (verb from the EA sheet, never invented) / `eaten` (press observed, picture did not respond — lag, animation lock, menu; **not** a console-fault claim) / `unlabeled`. Jev fan-out: `mode_pick` Choice over EA candidate modes + `no_match`, `press_efficacy` Noul, `conflict_pick` Choice. Code resolves the picked mode back through the EA sheet; Jev never emits a verb string. Attaches `press_label` to observation wires (`deck/observation_wire.py`).

**Two passes per press.** The wire label is provisional — `eaten` may not fire without after-evidence. A labeler-owned worker (`press-labeler-after`) then waits for the first `VisualContext` produced at least ~0.4s after the edge (latency-corrected via `latency_ms`), samples its `visual_phase` as `phase_after`, and re-judges: `eaten` now means *observed* non-response, while a missing post-press sample stays `unlabeled` (never a second model call to say "still nothing"). Verdicts (`verdict: True`, with `provisional` embedded) ride later wires as `press_verdicts`, land in `logs/press_labels/press_labels.jsonl`, and count under `press_labeler.verdicts`/`after` in `/health`.

---

## Key URLs

- https://scoreboard-ocr.com/faq — last-good freeze as feature (gap inverse)  
- https://github.com/mmlTools/fly-scoreboard/ — authored scorebugs  
- https://gpadtester.net/gamepad-viewer/ — pad display without HDMI join  
- https://github.com/Sherin-SEF-AI/CHRONYX-CORE — monotonic multi-sensor join (method adjacent)  
- https://dev.to/applekoiot/evidence-grade-telemetry-sensor-sync-time-bases-and-idempotent-ingestion-2g15 — evidence-grade clock discipline  
- https://retrorgb.com/understanding-capture-card-input-latency.html — capture lag discourse  
- https://knowledge.offworld.live/articles/5059810-spout-plugin-for-obs-studio — Spout subscribe pattern  
- https://github.com/obsproject/obs-studio/issues/12796 — browser freeze  
- https://streamlabs.com/content-hub/post/how-to-live-stream-to-twitter — X as RTMP destination  
- https://keepthescore.com/docs/streamdeck-integration/ — Deck as score bumper (contrast Integrity Board)  
