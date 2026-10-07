# Pages redesign notes — 2026 instrument site

Live today: https://conwan30.github.io/Qoresence/

## One design system (2026-10-07)

Operator direction: one look for the whole Pages site. **Colors and fonts are
Qoresence's** (Aperture Glass, same tokens as `glass/src/styles.css`);
**layout, glass plates, header, section rhythm, and motion come from the
Rivalatch door page**. Every `docs/*.html` page links exactly one stylesheet
(`docs/aperture.css`) and one script (`docs/site.js`). No page carries its own
`<style>` block or motion file. `trace.html` keeps its inline viewer script.

| Token | Value | Use |
|---|---|---|
| `--bg` void | `#05060a` | page |
| `--surface` well / `--subtle` plate | `#0b0d14` / `#12151e` | plates, wells |
| `--fg` star | `#e8eaf2` | headings, values |
| `--muted` iron | `#8b90a0` | body copy, small text (5.7:1 on plate) |
| `--dim` iron dim | `#5b6070` | decoration only (2.9:1 — never body text) |
| `--live` aperture | `#9be7ff` | primary action, current page, lodged/card |
| `--fast` brass | `#d7b36a` | held / HOLD, notices |
| `--veto` | `#e07a7a` | contested, "not" panels |
| `--font-display` / `--font-sans` | Instrument Sans 400/500/600 | display + body |
| `--font-mono` | IBM Plex Mono 500/600 | kickers, wire, codes |
| `--ease` | `cubic-bezier(0.23, 1, 0.32, 1)` | the only easing curve (hover 160ms, settle 620ms, draw 900ms) |

Status hues map onto that palette and always pair with a glyph, so they read
in grayscale: knock = iron ring, lodged = aperture ring+core, recalled = star
double ring, held = brass diamond+pin, contested = veto wedges + two-sided
press, no crown = iron dotted ring. Hold-loop marks reuse them: open = iron
ring, card = aperture core, HOLD = brass diamond, idle = iron dotted, dark =
iron bar.

**Shared pieces** (all in `aperture.css`): glass mast header with pill nav and
an opaque dropdown under 680px; kicker + display type scale; stacked section
heads; glass plates with a 2px tone rule and a 2px hover lift; the `q-stage`
(film tape + bracket + margin plates + step dots) used by both stages.

**Motion** (all in `site.js`): plates settle in once on scroll (70ms stagger,
then hand back to normal styles so hover still lifts); video plinths shutter
open once; two 16s beat stages share one engine:

- **Hold loop** (home, `[data-hold-stage]`): Open card → Card · opened once →
  HOLD (ident, not a game image) → Board not licensed □ – □ → Pad · Idle → No
  ConfirmTicket → not play (stage goes dark) → return. Labeled "Demo · HOLD ·
  not a live session". No digits, clock values, teams, or LIVE lamp.
- **Door loop** (Rivalatch, `[data-door-stage]`): Knock → Lodged 202 → held →
  Replay → Recalled 200 → Rival → Contested 409 → return. Example callers.

`prefers-reduced-motion: reduce` turns every animation and transition off and
shows one settled frame (home: No ticket; Rivalatch: Contested). Without JS the
markup is that settled frame and nothing starts hidden: reveal and shutter
only hide content under `html.q-motion`, which the script adds. Hidden tabs
stop the loop timers.

The old "flat void, no radial wash" deck law is relaxed for Pages only: a faint
aperture/brass ambient light sits behind content (no scanlines, no glow on
text). The Deck itself is unchanged.

**Fonts**: `docs/fonts/` now ships the five woff2 files that `aperture.css`
requests (copied byte-for-byte from `glass/src/fonts`) plus both OFL license
texts. The jsdelivr CDN fallback is gone; `@font-face` is local-only, so there
are no font 404s and no third-party font requests. See `docs/fonts/README.md`.

Retired: `docs/motion.css`, `docs/motion.js` (spring hold loop),
`docs/pages-next.css`, `docs/rivalatch-motion.css`, `docs/rivalatch-motion.js`.
`tests/test_rivalatch_pages.py` checks the one-stylesheet/one-script rule,
local font URLs, licenses, tokens, links, non-claims, and both loops.

## Motion stage (2026-10-03, superseded 2026-10-07)

Replaced by the Hold loop above (same eight states, now on the shared stage).
Kept for history.

The first hallway plinth is a hold loop, not a static logo. One iron shape
on the void (`#05060a`), no cuts: it changes size, radius, and content.
A drawn cursor clicks each change. `docs/motion.js` samples a closed-form
spring inside `seek(t)` — slight overshoot only, no CSS transitions, no
frame-to-frame motion state, no audio. 120 BPM, eight states, two seconds
each, sixteen seconds. The last frame matches the first, including the
cursor. `prefers-reduced-motion` keeps the static HOLD frame and does not
loop. The NCAA tape under the stage is unchanged. `docs/aperture.css` is
untouched.

| # | t | State | On the shape |
|---|---|---|---|
| 1 | 0s | Open | Control: “Open card” |
| 2 | 2s | Capture | Loader, label “Card” |
| 3 | 4s | Frame | Picture well, label HOLD. Aperture ident, not a game image |
| 4 | 6s | Board | Empty glyphs □ – □. “Board not licensed” |
| 5 | 8s | Pad | Stick at rest, label “Idle” |
| 6 | 10s | Ticket | Plate: “No ticket” |
| 7 | 12s | Dark | Well shutters closed, label “not play” |
| 8 | 14s | Return | Morphs back to Open so the seam matches |

Digits stay unlicensed. The loop never invents a score, a clock, a team,
or a LIVE lamp.

## Hallway (2026-09-01)

The public site is no longer a 12-section Deck parody. GitHub Pages is the
**door in front of the instrument** — HOLD chrome, one theater, honest blank.

| Route | Job |
|---|---|
| `docs/index.html` | One viewport. One sentence. One NCAA tape. Three actions. Four-row contrast. |
| `docs/watch.html` | Tape room: NCAA hour, HDMI/HID/IVC captions, Madden sidecars, Trace Viewer. |
| `docs/install.html` | Windows package + laptop proof command (`madden_27`, `age_s`, ConfirmTicket). |
| `docs/limits.html` | Claim ceiling, four glasses, FAQ, operator desk. |

Shared chrome: **Qoresence** wordmark (not “Retina Deck / local switcher”),
`SITE · HOLD` tally, “Board not licensed — this is a page.” No decorative PLL,
no wall clock, no fake LIVE. Fonts are self-hosted `docs/fonts/` (OFL, same
binaries as `glass/src/fonts`). Motion is one shutter open on the home/watch
plinth (`prefers-reduced-motion` skips it).

Old hashes (`#otel`, `#glasses`, `#privacy`, `#faq`, `#download`, …) redirect
from `site.js`. `#watch` and `#proof` stay on home.

`trace.html` and `dark.html` keep their bodies; chrome matches the hallway.

Do not promote overlay, Streamr, Twitch, or a launcher as the product face.

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

Watch demo (2026-08-30): `docs/assets/deck-live-demo.mp4` is a web transcode of the 2026-08-14 Edge window-capture (`Retina Deck — observation plane … 19-50-11.mp4`). Full 6m45s, 1280×720 H.264, no audio. Poster from the LIVE field at 00:12. Source file stays off-repo.

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

## Rivalatch door loop (2026-10-07)

Peer surface at `docs/rivalatch.html`. Same hallway chrome and spring-loop
discipline as the home hold stage; vocabulary is Lodged / Recalled / Contested
(prose only). CTAs point at the live Rivalatch door, MOBILE_KNOCKER, and listing.
Details: `docs/RIVALATCH_MOTION_NOTES.md`.

