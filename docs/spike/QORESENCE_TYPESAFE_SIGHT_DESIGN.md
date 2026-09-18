# Qoresence TypeSafe Sight Design — full freeze (NON-CLAIM)

Status: **design + faculty stamp LOCKED (2026-09-18)** — still no code until Operator GO. No code. Grounded in TypeSafe System One
(state + speculative fan-out + confidence-gated routing) and Qoresence hard laws.
Operator ConWan30 = HOLD. Qorector conducts; bots advise; Human HOLD beats PASS.

Date: 2026-09-18 CT  
Live packs already on main: TicketGlass (#223), SyncGlass (#224), ticket_stale (#222),
JevConductor / NoulObservatory / PressLabeler / RecapHygiene / SyncCoroner.

---

## 0. Intent

Make Qoresence feel like **one aperture, one clock, many glasses** that *vote*
rather than narrate. HDMI stays the eye. Jev never writes captions, PR bodies,
or score digits. Deck UI surfaces votes as glyphs + ClutchFeed land pulses so
the operator sees when the observatory saw something — without sports-scoreboard chrome.

Pain addressed:
- ClutchFeed posts land while Theater owns attention → feed feels empty.
- TicketGlass / SyncGlass already vote on `/health` → SPA ignores them.
- Next match priority: real-time scorebug lock + button-accurate labels on video clock
  (agents learn from licensed loops) — UI must never invent those labels.

---

## 1. Hard laws (immutable)

1. `licenses_digits: false` on every Jev pack forever.
2. Confirm ticket + `score_vlm_locked` = **only** path that paints score digits.
3. Jev may **force dark / block paint** — never unlock or mint digits.
4. Observation plane: no bus emit, no lobe locks, no capture-path blocking; timer/worker.
5. Local deterministic fallback; missing `TYPESAFE_API_KEY` must not break `--play`.
6. No Truth-plane / QorTroller wrap in state; no authorship / THROW / anti-cheat / humanity.
7. Pattern B: OBS uses `overlay.html` only; never dual-open DShow.
8. DualSense Edge: USB→laptop observe + BT→PS5 play; equalize via `syncLagMs` / `hidAt`.
9. Human HOLD beats every PASS. Auto-post / auto-merge on high Noul alone = forbidden.
10. Same URLs forever: `/` `/deck.html` `/overlay.html` `/studio.html` `/mobile.html` `/video` `/health` `ws` `/retina`.

Confidence gates (Operator): ≥0.7 act · 0.4–0.7 soft · <0.4 observe.

---

## 2. TypeSafe architecture for Qoresence

**Vote not voice.** Each glass owns a compact JSON `state` + parallel typed questions
(Choice / Score / Noul). Code owns consequences (glyphs, dock expand, dark board).

Patterns (from TypeSafe docs):
- Speculative fan-out — one `system_one` call per pack tick.
- Confidence-gated routing — soft glyphs vs act vs HOLD.
- Composite scoring — UI opacity / plinth heat from multiple scores in *code*.

Never:
- Replace scorebug VLM with Jev.
- Let Jev write @Qoresence captions or PR bodies (PressLabeler chooses *labels* only).
- Feed pixels / JPEG / Truth wrap into state.

Cadence: 200–300 ms situation tick or slower advisory timer; never on grab thread.

---

## 3. Sight Glass UX — Honesty Deck (primary ship)

### 3.1 Honesty strip (`#honestyStrip`)

Always-on ~32px bar under `#cmd` or above `#feedDock`.

| Source | Glyph | Meaning (UI only) |
|--------|-------|-------------------|
| TicketGlass | `lock` | board paint allowed / blocked / soft |
| TicketGlass | `tension` | lens_tension 0–3 → glow |
| TicketGlass | `cut` | clip_now licensed pulse |
| SyncGlass | `bind` | pad↔picture co-occur |
| SyncGlass | `lag` | lag_class chip |
| SyncGlass | `haptic` | vibration co-occur |

Visual rules:
- Opacity = confidence bands (≥0.7 solid, 0.4–0.7 dim, <0.4 ghost).
- Jev down / pack disabled / health missing → **strip dark** (fail-closed, never fake green).
- No numeric scores, no team abbrev invented from Jev.
- Tooltip = enum string from health only (e.g. `lag=capture_starve`), never prose LLM.

Wire: extend existing `/health` poll (~1500 ms) in `deck.html` to read
`h.ticket_glass.glyphs` + `h.sync_glass.glyphs` (+ conf if present). Do not add a
second poll storm.

### 3.2 ClutchFeed as landed pulse

Root cause: `#feedDock` max-height ~168px, Theater-focused layout, `addMoment` prepends
but does not demand attention when operator is on Theater / Session / cropped window.

Fix (code owns layout):
1. On `addMoment` for licensed clutch / confirm / clip: set `data-landed="1"` on newest row;
   bump `#feedDock` to expanded height for ~6s; scroll feed to top.
2. Theater mode: collapse feed to **peek strip** (1 row + count); on land → peek expands
   to 3 rows then collapses; optional one-line toast (template Choice from JevConductor
   only — never a scoreline).
3. HOME mode: full ClutchFeed + Honesty strip as operator desk.
4. If `ticket_glass.glyphs.lock === 'blocked'` OR `board_paint_block` high-conf veto:
   rows render digit-silent (□–□ / omit score fields). Existing Madden abbrev gate stays.

Hooks to reuse: `#feedDock`, `#feedCount`, `addMoment`, `handle` snapshot merge,
existing clutch-row CSS in glass SPA / `holo-plinth[data-clutch=near|hot]`.

### 3.3 Tension → Theater chrome

Map TicketGlass `lens_tension` (0–3) + SyncGlass `severity`:
- 0: chrome nearly invisible (operator play-eye first).
- 1–2: soft plinth / frame edge.
- 3 + cut glyph: brighten plinth only — **no** 12-stat overlay.

Boring sessions stay quiet. Clutch sessions light the aperture.

### 3.4 Digit law in UI

| Signal | UI may |
|--------|--------|
| confirm ticket + `score_vlm_locked` | paint digits from ticket |
| TicketGlass `board_paint_block` ≥0.7 | force dark / □–□ |
| soft_board alone | never paint as live score |
| Jev Choice/Score | glyphs, route, opacity only |

---

## 4. Aesthetic system (observatory, not broadcast)

Tokens (proposal for Qoreglass / Qorefront):
- **Surface:** deep slate glass (`rgba(12,17,24,.82)`), hairline `--line`, inset highlight.
- **Type:** Instrument Sans UI · IBM Plex Mono for codes/counts (already in Deck).
- **Motion:** 180–240 ms ease-out land; no bounce; no confetti.
- **Color:** cyan = bind/ok · amber = soft/tension · magenta = cut/clutch · dim gray = observe/dark.
- **Metaphor:** telescope aperture iris — glyphs are instrument readouts, not emotes.
- **Negative space:** Theater maximizes HDMI; chrome earns its pixels via tension.

Mobile: single row of 6 micro-glyphs + feed peek; never steal vertical from picture.
Overlay / X Live: **Honesty strip OFF by default** (Deck-only). Stream stays picture+licensed overlay.html only.

---

## 5. Pack inventory + next judgment packs

### 5.1 Live (keep)

| Pack | Flag | Role |
|------|------|------|
| JevConductor | `--jev` | moment template Choice (speech license only) |
| NoulObservatory | `--noul` | observatory nouls |
| PressLabeler | under jev | press *label* pick — not caption prose |
| RecapHygiene | under jev | recap digit hygiene vote |
| SyncCoroner | under jev | sync death cause |
| ticket_stale | `--jev-ticket-stale` | soft_board freshness vs confirm |
| TicketGlass | `--ticket-glass` | lock/tension/cut + paint veto |
| SyncGlass | `--sync-glass` | bind/lag/haptic (advisory) |

### 5.2 Proposed new packs (NON-CLAIM until Qoreeval→Qoretrust)

Ship order after Honesty UI lands. Each: questions file + worker + `/health` + tests +
default-off + `licenses_digits: false`.

#### A. FeedGlass (ClutchFeed honesty) — **next after UI strip**
Owner design: Qoreglass · impl: Qorefront · judgment: typesafe-ai  
State: last N moments (title template id, age_ns, digit fields present?, ticket locked?).  
Questions:
- `row_may_show_digits` Noul — only if ticket-clock already locked (else force false in code)
- `moment_class` Choice — clutch / score_lock / clip / noise / unknown
- `surface` Choice — home_rail / theater_peek / toast / suppress
- `salience` Score 0–3 — how hard to pulse the dock  
Glyphs: `feed` / `pulse` / `mute`  
Consequence: drives dock expand + mute noisy duplicates — **never** writes row text.

#### B. LabelGlass (button-accurate Madden/CFB labels on video clock)
Aligns operator next-match goal.  
State: HID edge names last N, frame_seq, title profile, Outcome profile id.  
Questions:
- `label_family` Choice — face / shoulder / stick / dpad / system / unknown
- `label_ok_for_loop` Noul — safe to show as co-occur label (not authorship)
- `sync_to_picture` Noul — edge couples to recent picture motion  
Hard: labels are co-occurrence chips on video clock; never “player intended X”.

#### C. TheaterGlass (chrome economy)
State: mode home|theater|session, lens_opacity, tension, x_live, mobile_connected.  
Questions: `chrome_budget` Score 0–3 · `plinth_heat` Choice cold/warm/hot · `steal_eye` Noul  
Consequence: CSS data-attrs only.

#### D. ClipGlass (Foundry ring)
State: clip_now glyph, buffer age, last cut reason, digit lock.  
Questions: `keep_ring` Noul · `picture_match` Noul · `export_ready` Choice hold/ready/block  
Qorefoundry consumes; no auto-post.

#### E. AgentSpeakGlass (AgentGlass gate)
State: moment_class, lock, coupling tickets, A2A license flags.  
Questions: `may_speak` Noul · `channel` Choice deck/a2a/suppress · `verbosity` Score 0–2  
Qoreagent: agents speak only when licensed; silence is success.

#### F. RecapGlass (export door hygiene — observation only)
Tightens RecapHygiene with UI-facing seal readiness; still no Truth wrap; seal stays
QorTroller after gamer consent (Qor Clock plane).

Spike rule: Qoreproto may prototype on `spike/*` — never ride `--play` until promoted
via Qoreeval → Qoretrust → … lab ring.

---

## 6. Bot ownership matrix (background design)

| Bot | Role in this freeze |
|-----|---------------------|
| **Qoreglass** | Aesthetic tokens, Honesty strip + Feed land visual language |
| **Qorefront** | Implementability: `deck.html` /health poll, `#honestyStrip`, `addMoment` expand |
| **QorThink** | Rank next packs; novelty metaphors under hard laws |
| **Qoremobile** | Mobile glyph row + feed peek |
| **Qorex** | Keep Honesty **off** X/stream; digit-silent when blocked |
| **Qorelive** | Audience path: Deck-only vote chrome |
| **Qorefoundry** | ClipGlass consumption / ring highlight on `cut` |
| **Qoreagent** | AgentSpeakGlass gate |
| **Qoreclock / Qorehaptic** | Facts only into SyncGlass state; no duplicate clocks |
| **Qoreoutcome** | Title/profile facts into TicketGlass / LabelGlass state |
| **Qoreeval / Qoretrust** | Promote packs; fail-closed audit |
| **Qoreproto** | Spikes only; NON-CLAIM |
| **Qorector** | Conductor; RCP envelopes; no merge without Operator GO |

Ticketed this turn: Qoreglass, Qorefront, QorThink, Qoremobile, Qorex, Qorefoundry,
Qoreagent; FYI held for Qorelive.

---

## 7. Ship ladder (smallest → larger)

1. **Sight Honesty v0 UI** (no new Jev pack): wire glyphs + ClutchFeed land pulse + digit-silent.
2. **FeedGlass** pack (judgment for surface/salience).
3. **TheaterGlass** chrome economy.
4. **LabelGlass** (button-accurate co-occur labels) — next match learning loop.
5. **ClipGlass** + **AgentSpeakGlass**.
6. Recut UI tour with Honesty strip + Feed land on camera (Qorex re-gate; Post HOLD).

Each step: design freeze → Grok Build + typesafe-ai → feat/* PR → CI → Operator GO merge
→ MyTurn pull → `/health` prove → Deck prove.

---

## 8. Deck implementability sketch (for Qorefront)

Files: `qoresence/deck/deck.html` (primary), optional glass SPA shared CSS.

```text
/health poll (existing ~1.5s)
  → paintHonesty(h.ticket_glass, h.sync_glass)
  → if missing: honestyStrip.dataset.state = 'dark'

addMoment(p)
  → prepend row
  → if p.action in {clutch,confirm,clip} OR salience≥2:
       feedDock.dataset.expanded = '1'
       clearTimeout → collapse after 6s
       row.classList.add('land')
  → if digitsBlocked(h): strip score fields from row paint
```

No WebSocket required for v0. No grab-thread work. No new Python for step 1.

---

## 9. Success criteria

- Operator can glance Deck and know lock/bind/lag without opening `/health` JSON.
- When ClutchFeed posts, the feed **moves into view** within one land animation.
- Theater stays picture-first; boring sessions stay quiet.
- Zero invented scores; blocked lock ⇒ □–□.
- New packs default off; `--play` alone unchanged.
- Stream / overlay never grow vote chrome by default.

---

## 10. RCP envelope (this freeze)

- path: confirm (design)
- plane: qoresence-observation
- kind: patch (design freeze)
- evidence: TicketGlass/SyncGlass live health glyphs; `#feedDock`/`addMoment` in deck.html;
  TypeSafe how-to-build (code owns control flow; atomic questions; confidence gates)
- HOLD: implementation + merge until Operator GO on ship ladder step 1+


---

## 11. Faculty stamp — 2026-09-18 CT (LOCKED)

Inputs folded from: Qoreglass · Qorefront · QorThink · Qoremobile · Qorex · Qorefoundry · Qoreagent.
Status: **aesthetic + implementability freeze stamped**. Still no code until Operator GO.

### 11.1 Conflict resolutions (Director)

| Conflict | Resolution |
|----------|------------|
| Qoreglass: overlay 6-glyph under SYNC vs Qorex: overlay MINIMAL/OFF | **Qorex wins for public.** Overlay / audience-live: Honesty strip **OFF by default**. Optional single quiet void chip (`blank` / `confirm pending`) only — never 6-glyph theater, never score digits in glyph. Deck + Mobile keep full/thin Honesty. |
| Legacy `#feedDock` vs SPA `clutch-feed.tsx` | **SPA is primary** (Qorefront). Wire Honesty + land pulse in glass SPA. Legacy `deck.html` `#feedDock` is secondary parity only; do not dual-maintain forever. |
| Qoreglass LAG shows measured ms | Allowed: measured `syncLagMs` tabular from **code facts**, not Jev-minted. Still no score pairs / □–□ in Honesty strip. |
| Foundry captions on cut | **Receipt only** (path, clock_ns, frame_seq, crop_hash, reason). No prose story; digits only if ConfirmTicket+lock+fresh. |

Digit law (all public + operator glasses), shared:
`ConfirmTicket` + `score_vlm_locked` + ticket-fresh `crop_hash`.  
`board_locked` alone never licenses. TicketGlass `board_paint_block` / blocked lock → digit void.  
**Blank beats hold beats guess.** Wrong score on X/Live lives forever.

### 11.2 Aesthetic freeze (Qoreglass) — tokens LOCKED

Colors: void `#05060a` · well `#0b0d14` · plate `#12151e` · star `#e8eaf2` · iron `#8b90a0` · iron-dim `#5b6070` · aperture `#9BE7FF` · brass `#D7B36A` · veto `#E07A7A`  
Type: Instrument Sans UI · IBM Plex Mono chips/glyphs (tabular).  
Motion: micro 80ms · quick 150ms · land 230ms one-shot · dock expand 150ms in / 400ms out · ease-out. Bloom ≤12px chrome-only. Picture never glows.  
Opacity: solid 1 · dim 0.55 · ghost 0.35.

HonestyStrip (~32px): order L→R **LOCK · TENSION · CUT · BIND · LAG · HAPTIC**.  
Placement: under CommandBar, above HDMI+aside split — **never inside HdmiStage**.  
`data-honesty=live|dark` · `data-glyph=…` · `data-conf=solid|dim|ghost`.  
Jev-down / Dark Theater → entire strip dark (mounted, dead).

ClutchFeed landed pulse (Theater): peek 40–48px → expand ~2.4s on licensed land → ease to peek; brass/aperture hairline flash even when collapsed. HOME = full rail. Unlicensed = no expand.

Tension→plinth: reuse `.holo-plinth[data-clutch=near|hot]` only.

### 11.3 Implementability freeze (Qorefront) — LOCKED for cut

- Poll `/health` via existing `monitor.ts` (or light parallel GET) — **never** touch ensureCapture / JPEG /video / WS decode.
- Store ingest fail-closed (missing → enabled:false, strip dark).
- SPA: `clutch-feed.tsx` landKey; extend expand/peek; Theater peek chip optional.
- `board_paint_block` OR lock=blocked → OR into pickBoard consumers (digit-silent).
- Files sketch: `honesty-health.ts` / store ingest / HonestyStrip component / situation-card / digit-integrity void reason.
- Out of scope step-1: Python deck rewrite, auto lag recenter, JSONL.

### 11.4 Mobile (Qoremobile) — LOCKED

HonestyGlyphRow 28–32px below command, above stage. ClutchFeedPeek ≤48px collapsed / max 3 rows expanded. Stage ≥70% portrait. Tap glyph = 1-line reason toast, no digits.

### 11.5 X / Live (Qorex) — LOCKED

TicketGlass block → public digit silence. Captions digit_silent; Create≠Post; no Honesty vocabulary in public copy. `--x-glass` default OFF. Overlay blank score cells > badge theater.

### 11.6 Foundry (Qorefoundry) — LOCKED

TicketGlass `cut`/`clip_now` **arms** ring export only when ticketLive + ConfirmTicket + ticket-fresh crop_hash. Rate limit 10s. Empty ring → `clip_unavailable` fact, never synthetic MP4. Surface = **clip receipt** chip only. Foundry lobe default OFF.

### 11.7 AgentGlass (Qoreagent) — LOCKED

Honesty conflict (`observationConflict`) → VETO A2A bind/heat/sheet claims (silence or non-claim hold).  
moment_class gates: idle→quiet; soft→presence only; heat→coupling ticket; board/score→confirm+lock+fresh; mismatch→quiet.  
Order: lobe OFF / HOLD / emit-under-lock → quiet; then honesty veto; then moment_class; then license_gate; then MCP `may_say` intersect.

### 11.8 Ranked enhancers (QorThink) — land order UPDATED

1. **Sight Honesty v0 UI** = ClutchFeed Presence + glyph surface (Deck) — fixes stated pain  
2. TicketGlass freshness UI (stale chip Deck / hard blank public)  
3. SyncGlass/SyncCoroner glyph-only (already live health; surface it)  
4. FeedGlass judgment pack (surface/salience)  
5. JevConductor as glass broker (opt-in)  
6. LabelGlass (button-accurate co-occur)  
7. ClipGlass + AgentSpeakGlass  

HOLD forever: replace VLM with Jev; Truth-plane; dual-open; `--x-glass` default ON.

### 11.9 Ship ladder step 1 (cut when Operator GO)

**feat/sight-honesty-ui** — SPA only:
1. HonestyStrip from `/health.ticket_glass` + `/health.sync_glass`
2. ClutchFeed peek/expand land pulse (Theater)
3. Digit-silent OR from `board_paint_block` / lock=blocked
4. Tension → plinth data-clutch
5. Tests: fail-closed missing health; licenses_digits false; no video-path touch

Owners: Qorefront impl · Qoreglass aesthetic sign-off · Qorector review · Operator merge HOLD.

