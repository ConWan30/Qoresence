# Rivalatch motion door — Qoresence Pages

Date: 2026-10-07 · Author: Grok Bot (Pages motion front end)

Live path: https://conwan30.github.io/Qoresence/rivalatch.html

## Intent

A Rivalatch-themed motion surface on the Qoresence GitHub Pages hallway,
without inventing Spec fields, without embedding API keys, and without claiming
a live Ship session. Public name **Rivalatch**; wire identifiers stay VibeGate.

## Design language

The page started in the design language of [ConWan30/Gloss](https://github.com/ConWan30/Gloss)
(tape, bracket, margin plates, marks). On 2026-10-07 it moved onto the
Qoresence palette and fonts, and its layout and motion became the system for
the whole Pages site (see `docs/PAGES_REDESIGN_NOTES.md`, "One design
system"). Gloss content is not copied.

| Gloss idea | Rivalatch door |
|---|---|
| Live tape strip | Knock tape: example callers A / B with key `k-01` advance under the door |
| Window bracket | Door bracket over the tape; its readout (`door k-01 · held \| incoming`) sits in the stage head beside the demo tag, so it never covers a frame |
| Reading plates in the margin | Answer plates: Lodged, Recalled, Contested (with `held \| incoming` lanes) |
| Marks (shape + one hue) | Door tags (shape + one hue), see below |
| Clash (two pressures, neither crowned) | Contested 409: held vs incoming, no crown |
| Hold (sealed) | The held story (first caller); Occupied = 409 held |
| Echo (same reading, other words) | Recalled 200: same key + payload returns the same job |
| Caption / demo tag | "Demo · example knocks · not live" tag + example wire readout |

Tokens and fonts are the shared Qoresence ones in `docs/aperture.css`
(Instrument Sans + IBM Plex Mono, self-hosted).

### Door tags

| Tag | Wire | Glyph | Hue (token) |
|---|---|---|---|
| knock | `gate.run` | hollow ring (breathes while open) | iron `#8b90a0` |
| lodged | 202 | ring with a core | aperture `#9be7ff` |
| recalled | 200 | two overlapping rings | star `#e8eaf2` |
| held / occupied | 202 held story / 409 held | sealed diamond + pin | brass `#d7b36a` |
| contested | 409 incoming | two wedges meeting + two-sided press | veto `#e07a7a` |
| no crown | — | dotted ring, dashed plate | iron `#8b90a0` |

Knock and no crown share a hue but never a glyph (ring vs dotted ring, solid
vs dashed plate). All hues are at least 5.7:1 on the plate color.

Prose tags only. HTTP numbers are the frozen door (`202` / `200` / `409`).
No GateResult / OpenAPI / MCP tool invention.

## Motion

One settle curve (the site `--ease`, `cubic-bezier(0.23, 1, 0.32, 1)`), 400–900ms, no
bounce, no neon glow. A plate animates only when it is new (`is-new`, 620ms
settle) or when its tag changes (`is-remarked`, one soft ring; held plays one
900ms seal). Contested keeps a slow two-sided press; knock breathes. The tape
advances linearly with `transform` only (32s). Sections settle in once on
scroll (IntersectionObserver, 70ms stagger); the request line in "The rule,
drawn" draws once. Hover: surfaces lift 2px with an aperture edge (160ms).

Door loop (`site.js`, `[data-door-stage]`), 16s period, eight 2s beats:

| # | t | Beat | Stage |
|---|---|---|---|
| 1 | 0s | Knock | Caller A, new key; plates vacant |
| 2 | 2s | Lodged | Plate A settles · 202 |
| 3 | 4s | held | Plate A seals gold · the held story |
| 4 | 6s | Replay | Plate R: same key · same payload |
| 5 | 8s | Recalled | Plate R re-marks · 200 · no second ship |
| 6 | 10s | Rival | Plate B: same key · different payload |
| 7 | 12s | Contested | Plate B · 409 · held \| incoming lanes (Occupied · Contested) |
| 8 | 14s | Return | Plates clear; loop returns to Knock |

`prefers-reduced-motion: reduce` stops every animation and transition and shows
the settled Contested frame (also the no-JS markup). Hidden tabs stop the
timers. Without `backdrop-filter`, plates fall back to opaque fills.

## Visualizations (no fabricated metrics)

- **Door stage**: example knocks, labeled "Demo · example knocks · not live".
- **The rule, drawn**: decision grid (key new/seen × payload same/different →
  202 / 200 / 409). This is the frozen behavior, not traffic data.
- **One knock, three calls**: `gate.run` → `gate.status` (poll) →
  `gate.get_result`, plus the optional HMAC webhook (fail-closed).

## Files

| Path | Job |
|---|---|
| `docs/rivalatch.html` | Door hallway page + CTAs |
| `docs/aperture.css` | Shared site stylesheet: tokens, fonts, plates, `q-stage`, motion |
| `docs/site.js` | Shared site script: menu, reveal, door + hold loops; exports `door` / `hold` / `beatAt` for tests |
| `docs/assets/rivalatch-icon.jpg` | Gate mark (from vibegate brand) |
| `docs/assets/rivalatch-lockup.jpg` | Social / lockup |
| `tests/test_rivalatch_pages.py` | Static checks for every page: one stylesheet/script, local fonts, links, no keys, demo labels, reduced motion, both loops |
| `docs/RIVALATCH_MOTION_NOTES.md` | This note |

## CTAs (public only)

- Door: https://vibegate-production.up.railway.app
- Door board: https://vibegate-production.up.railway.app/door/
- AGENT.md: https://vibegate-production.up.railway.app/AGENT.md
- MCP.md: https://vibegate-production.up.railway.app/MCP.md
- MOBILE_KNOCKER: https://vibegate-production.up.railway.app/MOBILE_KNOCKER.md
- Listing: https://vibegate-production.up.railway.app/listing/

Auth is named (`X-Api-Key`) but never valued on Pages.

## Non-goals

- Spec / OpenAPI / GateResult changes
- Secrets, challenge tokens, or example API keys in HTML/JS
- X posts or merge-to-main without operator Proceed
- Claiming this page is a live knock surface (it is a door loop + outbound links)
- Live metrics or counts (none are published; none are drawn)
