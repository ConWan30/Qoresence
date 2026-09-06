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

0. **SEQGATE v0** — named frame-license harness over Null Digit + ticket-fresh + capture lease. See [SEQGATE.md](SEQGATE.md). Ident Latch (#145) stays HOLD. Integrity Board tiles stay empty (HOLD note).
1. **Null Digit Glass + Ticket Freshness Strip** (honest scorebug law visible on program)  
2. **Single-Open Lease + Subscribe-Only Spout Contract** (lag/freeze↓ + dual-open death)  
3. **Deck Integrity Board + Skew Alarm** (operator delight without score bumping)  
4. **Coupling Meter Glass** (pad↔picture sync as presence evidence)  
5. Keep **Presence Lattice / Bookmarks / Receipts** behind default-OFF lobes with vocabulary lint

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
