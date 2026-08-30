# Pages redesign notes — 2026 instrument site

Branch: `feat/pages-redesign-2026`  
Live today: https://conwan30.github.io/Qoresence/ (still the previous long-scroll until this lands on `main`).

## Aperture Glass migration (2026-08-30)

The public site now mirrors the Retina Deck's **Aperture Glass** token system
(`glass/src/styles.css`) instead of the earlier "night field-ops / phosphor
broadcast" palette. One aesthetic for every surface — the operator Deck and the
GitHub Pages site share the same machined iron chrome.

| Before (phosphor broadcast) | After (Aperture Glass) |
|---|---|
| Phosphor green `#c6f26a`, signal teal `#4fe0d4` | Aperture cyan `#9be7ff`, brass clutch `#d7b36a`, veto `#e07a7a` |
| Scanlines + radial wash on `body` | Flat void `#05060a` — no scanlines, no radial wash (deck law) |
| Syne (display) + Sora (body) | Instrument Sans (display + body) + IBM Plex Mono (data) |
| Broadcast pills, radii 16–28px | Machined plates, radii 2–12px |
| Green-tinted hairlines | Iron hairlines `color-mix(in oklab, #8b90a0 22%, transparent)` |
| Inline `<style>` per page | Shared `docs/aperture.css` (single source of truth, mirrors the deck's one `styles.css`) |

## Operator glass layout (2026-08-30)

The token port was not enough — the public site still read as a marketing
scroll. This pass copies Retina Deck *chrome*, not just the palette:

- Command bar (`holo-header`) with Q mark, **Retina Deck / local switcher**,
  STANDBY tally, glass-nav tray, and 01/02/03 stream keys.
- Status strip is HOLD on purpose: `PLL open · couple none`, `□–□ · — & —`,
  `PAD unbound / HDMI wait / MONITOR WAIT / SYNC UNBOUND`. Never fake LIVE.
- Proof/Watch is a theater: HDMI `holo-plinth` + Situation / Clutch Feed rail
  — same split as `TheaterPage` (`hdmi-stage` + intel column).
- Iron signal prism under the picture (HOLD fill, not iris freshness).
- Content / IA / claim ceiling unchanged. Product stays local-first.
- Inner pages (install / dark / trace) share the same command bar. Single-column
  heroes collapse the two-col `gap` so lede sits under the title, not 80px away.

Deck laws that carried over:
- **Flat void field.** No scanlines, no radial wash, no bloom on the picture.
- **Machined chrome.** Iron hairline borders, flat plates, aperture bloom ≤ 12px
  only on the spine pulse (decorative iron, not content glow).
- **One-shot motion.** `cubic-bezier(0.23, 1, 0.32, 1)`, 80–400ms tiers.
  `prefers-reduced-motion` kills ambient motion.
- **Path tints.** Brass `#d7b36a` = fast, aperture `#9be7ff` = confirm — same as
  the Clutch Feed `data-land` rule in the deck.
- **HOLD on the public site.** Empty glyphs stay empty. No invented 0–0.

Files touched:
- `docs/aperture.css` — new shared token system (ported from `glass/src/styles.css`).
- `docs/index.html` — links `aperture.css`; content/IA unchanged.
- `docs/install.html` — links `aperture.css`; content unchanged.
- `docs/dark.html` — links `aperture.css`; content unchanged.
- `docs/trace.html` — links `aperture.css`; table gets `class="spans"`; timeline
  caption updated from "phosphor/signal" to "aperture/iris".

## Audit of the previous `docs/index.html`

**Kept (it already worked):**
- Night field-ops palette (phosphor / signal / confirm / alert)
- Syne + Sora + IBM Plex Mono
- Clock-spine instrument in the hero
- Deck demo MP4 + poster (`docs/assets/deck-live-demo.*`)
- Principle line: *The capture card is the brain. Everything else is a glass.*
- Mobile hamburger, reduced-motion kill-switch

**Gaps the prompt called out:**
- One technical scroll with three use-cases and no contrast / privacy / FAQ / profiles
- Demo sat in a bare `<video>` without a bezel / meta strip
- MCP tool count was stale (10 vs 12)
- No Open Graph / Twitter cards
- Install nav pointed at a dead `#surface` anchor
- No community or sibling-plane pointer

## What changed

| File | Change |
|---|---|
| `docs/index.html` | Full IA rewrite, same tokens. Sticky nav + scroll progress + active section. Hero chips. Cinematic demo chrome. Clock-spine row. Orchestration 01–05. Five glasses (MCP = 12 tools, wrap dest named). Capabilities 8-up. Profiles. Honest contrast table. Pilot gates. Privacy / non-goals. Install band. Community. FAQ. |
| `docs/install.html` | Theme color matches home. Nav → Glasses / Pilot gates / Limits. Footer carries the principle line + wiki. |
| `docs/PAGES_REDESIGN_NOTES.md` | This file. |

Assets reused (no new generated art): `deck-live-demo.mp4`, `deck-live-demo.jpg`, `qoresence-social-preview.png`.

## Content assumptions (shipped on `e8ecbab` / current `main`)

- Title-presence is **on with `--play`** (later than the r02 HOLD packet).
- MCP has **12** tools including `get_observation` and grant-gated `wrap_observation`.
- Wrap dest is **`qoresence-research` only**; `qortroller-truth` / `*-truth` denied.
- DriveGraph default cap **48**, floor 8, ceiling 96.
- Madden is first-class (own crop + local roster). Ambiguous last names stay empty.
- Mobile Glass: WebRTC → MJPEG, `127.0.0.1` default, LAN via `--deck-bind 0.0.0.0` + Theater QR.
- Windows-first public pilot. No Discord is claimed.
- QorTroller is linked as the sibling **truth** plane, never merged into Qoresence claims.

## Deliberate non-claims

- No fake live telemetry. The spine pulse is decorative only.
- No “AI proves skill”, no cloud anti-cheat, no DePIN as core story.
- No private LAN IPs.
- No new Discord / social invent.

## How to preview

```powershell
cd C:\Users\Contr\Qoresence
# static: open docs/index.html, or
python -m http.server 5500 --directory docs
# then http://127.0.0.1:5500/
```

Operator reviews this branch before merge to `main` (Pages deploys from `docs/` on `main` push).
