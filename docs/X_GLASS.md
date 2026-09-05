# Qoresence Live 0.9.0 — X Glass

**Status: product face only.** This document names the Live 0.9.0 pivot. It does **not** ship a runtime lobe. There is no `--x-glass` flag on `main`. There is no `qoresence/x/` package. DualSense stays on the PS5.

## Pivot

| Layer | Role | Status |
|-------|------|--------|
| Local causal plane | Brain — capture card, tickets, Foundry, Sight Glass | Shipped |
| X Live Studio | Pixel glass — audience video via OBS Custom RTMP | Shipped recipe ([X_LIVE_STUDIO.md](X_LIVE_STUDIO.md)) |
| X API | Future memory / receipt glass — conversation + Timeline VOD receipts | **Default OFF. Not implemented.** |

Qoresence remains a **local observatory for X**. Live pixels never leave OBS. Timeline VOD / Posts never invent digits.

## What X Glass is (when it ships)

A **default-off** future lobe that:

- **Reads** the causal bus + Foundry clip / receipt artifacts
- **Writes** only to the **X API** and **local receipt logs**
- **Never** opens DirectShow / the capture card
- **Never** pushes RTMP (OBS owns audience RTMP)
- **Never** holds the streamer lock

Until that lobe exists, treat every `--x-glass` / `--x-listen` mention below as **documentation of intent**, not CLI that works today.

## Two pipes

| Pipe | Owner | What it carries | Canonical id |
|------|--------|-----------------|--------------|
| **Live (pixels)** | OBS → X Live Studio (Custom RTMP) | HDMI glass + Clutch Lens overlay | Once posted: `https://x.com/i/broadcasts/…` |
| **VOD / conversation (receipts)** | Future X Glass → X API | Timeline posts, clip receipts, session memory | Same broadcast URL when bound; else local Foundry paths only |

Onboarding for pixels (Pattern B): **[X_LIVE_STUDIO.md](X_LIVE_STUDIO.md)** — that is Live step 2. This file is the product face for the whole Live 0.9.0 story and the future API glass.

## Claim ceiling (public Posts)

Digits, heat, and pad glyphs may appear on **public** X Posts **only** when all of these hold:

1. `ConfirmTicket` present
2. `score_vlm_locked`
3. Ticket is **fresh** (`crop_hash` match / Same-Seq / clock age — same law as the Lens)

Otherwise: **blank glyphs or silence**. Prefer empty over a held stale board.

**Language:** co-occurrence, coupling, presence evidence.  
**Never:** authorship, anti-cheat, humanity, eligibility, on-chain default, Truth-plane / QorTroller wrap.

## Phase status

| Phase | Intent | Status |
|-------|--------|--------|
| **0** | Pattern B ownership + Live Studio recipe + public overlay digit gate | **Done** — [X_LIVE_STUDIO.md](X_LIVE_STUDIO.md), Lens `overlay.html` |
| **1** | Bind broadcast URL as session public id (operator paste / grant) | Not shipped |
| **2** | Fail-closed Timeline receipt from Foundry (opt-in grant) | Not shipped |
| **3** | `--x-glass` publish lobe (default OFF) | Not shipped |
| **4** | `--x-listen` conversation glass (default OFF) | Not shipped |
| **5** | Session header / Foundry reel Posts under grant | Not shipped |
| **6** | Live + chat APIs | **Only if** X publishes them; **no chat scraper** |

Phase order is **0 → 5**. Do not skip Phase 0 ownership when adding later phases.

## Flags (document only — do not implement here)

| Flag / control | Default | Note |
|----------------|---------|------|
| `--x-glass` | **off** | Future publish lobe. Not on CLI today. |
| `--x-listen` | **off** | Future conversation glass. Not on CLI today. |
| Grant id | required for publish | Operator grant before any Timeline write |

No OAuth tokens in git. No stream keys in Qoresence. No WHIP ingest. No Twitch revival.

## Hard laws (unchanged)

- Pattern B: Qoresence owns `USB3.0 Video`. OBS uses Browser Source only (`obs-live.html` + `overlay.html`). Never dual-open DShow.
- DualSense stays on the PS5. Empty laptop HID is success, not PAD WAIT.
- Fast path never invents scores. Confirm uses locked `last_confirm` / `score_vlm_locked`.
- No emit-under-lock. Capture thread does not wait on chat or HTTP.


## Console coupler

Three surfaces. Keep them separate. **Never paste keys, tokens, or stream keys into git or chat.**

| Surface | What it is | Role |
|---------|------------|------|
| **Live Studio (pixels)** | Human **Go Live** on [@Qoresence](https://x.com/Qoresence) | OBS Custom RTMP / RTMPS. The Live Studio **stream key is a Live Studio password**, not an Observatory console Keys-tab secret. The developer console does **not** provision RTMPS ingest. Bots never tap Go Live. |
| **Observatory app `33393205`** | Brand developer app **Qoresence Observatory** | Future default-off **X Glass** mouth: Posts, draft receipts, Timeline VOD, filtered-stream listen. OAuth 2.0 confidential (Web App / Automated App or Bot); **Read and write**; DMs off; email off. Brand mouth connector in Cursor: `user-X--qoresence` — never ConWanZo as the brand. |
| **ConWanZo app `33392974`** | Operator / personal app named "Qoresence" (name taken) | **Not** the public Live or API brand. Do not use `33392974` as the brand mouth. |

### Brand console facts (no secrets)

- Brand console account: **@Qoresence** developer program
- App name: **Qoresence Observatory** · App ID: **33393205**
- Callbacks (patterns only): `127.0.0.1/callback`, `localhost:8765/callback`, GitHub Pages
- Website / terms: GitHub Pages; privacy: GitHub repo
- Filtered stream rules (stored for a future `--x-listen`; **not** a Live Studio feature): brand rule (`Qoresence` OR `#Qoresence` OR `#GhostStick` OR `#DarkTheater`) plus a separate `from:Qoresence` row — **do not AND-combine** (ambiguous)
- Webhooks: empty / parked until public HTTPS CRC
- Chat bots: not registered (parked; DM-scoped)
- Console Agent: unused
- Automation: @Qoresence labeled automated, managed by ConWanZo
- Icon: ice-cyan Q app icon
- Exhibit: Grok review (do not claim approved unless verified)

Live Studio keys ≠ Observatory Keys. Pixel path stays [X_LIVE_STUDIO.md](X_LIVE_STUDIO.md). API / receipt path stays this file, default OFF, not implemented.

## Related docs

- [SPOUT_GLASS.md](SPOUT_GLASS.md) — FrameHub → Spout2 PGM for OBS (spike; default OFF; not X API)

- [X_LIVE_STUDIO.md](X_LIVE_STUDIO.md) — pixel onboarding (Live step 2)
- [OBS_OWNS_CARD.md](OBS_OWNS_CARD.md) — Pattern A vs B
- [ROADMAP.md](ROADMAP.md) — versioning + optional social checklist
- [CAPTURE_OWNERSHIP.md](CAPTURE_OWNERSHIP.md) — one card, one owner

---

*Live 0.9.0 = honest product face. Brain local. Pixels via Live Studio. Receipts later, fail-closed, default OFF.*
