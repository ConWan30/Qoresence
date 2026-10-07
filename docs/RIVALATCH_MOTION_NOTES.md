# Rivalatch motion door — Qoresence Pages

Date: 2026-10-07 · Author: Grok Bot (Pages motion front end)

Live path: https://conwan30.github.io/Qoresence/rivalatch.html

## Intent

A Rivalatch-themed motion surface on the Qoresence GitHub Pages hallway,
without inventing Spec fields, without embedding API keys, and without claiming
a live Ship session. Public name **Rivalatch**; wire identifiers stay VibeGate.

## Design language (Gloss)

The page uses the design language of [ConWan30/Gloss](https://github.com/ConWan30/Gloss)
(`docs/MOTION_NOTES.md`, `public/gloss.css`), adapted to the door. Gloss content
is not copied; only tokens, type, plate treatment, and motion rules.

| Gloss | Rivalatch door |
|---|---|
| Live tape strip | Knock tape: example callers A / B with key `k-01` advance under the door |
| Window bracket | Door bracket: label shows the key and the door's answer |
| Reading plates in the margin | Answer plates: Lodged, Recalled, Contested (with `held \| incoming` lanes) |
| Marks (shape + one hue) | Door tags (shape + one hue), see below |
| Clash (two pressures, neither crowned) | Contested 409: held vs incoming, no crown |
| Hold (sealed, gold) | The held story (first caller); Occupied = 409 held |
| Echo (same reading, other words) | Recalled 200: same key + payload returns the same job |
| Caption □ / demo tag | "Demo · example knocks · not live" tag + example wire readout |

Tokens are scoped to `body.rl` in `rivalatch-motion.css`. The shared Aperture
tokens (`--bg`, `--fg`, `--primary`, `--font-*`, …) are re-pointed on this page
only, so the site header/nav match without touching other Pages. Fonts are the
Gloss system stacks (serif display, system sans, ui-monospace); nothing is
fetched.

### Door tags

| Tag | Wire | Glyph | Hue |
|---|---|---|---|
| knock | `gate.run` | hollow ring (breathes while open) | `#b4aea2` |
| lodged | 202 | ring with a core | `#8fb898` |
| recalled | 200 | two overlapping rings | `#a698d2` |
| held / occupied | 202 held story / 409 held | sealed diamond + pin | `#e2c072` |
| contested | 409 incoming | two wedges meeting + two-sided press | `#d76d61` |
| no crown | — | dotted ring | `#8796a6` |

Prose tags only. HTTP numbers are the frozen door (`202` / `200` / `409`).
No GateResult / OpenAPI / MCP tool invention.

## Motion

Gloss rules: one settle curve `cubic-bezier(0.2, 0.7, 0.1, 1)`, 400–900ms, no
bounce, no neon glow. A plate animates only when it is new (`is-new`, 620ms
settle) or when its tag changes (`is-remarked`, one soft ring; held plays one
900ms seal). Contested keeps a slow two-sided press; knock breathes. The tape
advances linearly with `transform` only (32s). Sections settle in once on
scroll (IntersectionObserver, 70ms stagger); the request line in "The rule,
drawn" draws once. Hover: surfaces lift 2px with a gold edge (200ms).

Door loop (`rivalatch-motion.js`), 16s period, eight 2s beats:

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
| `docs/rivalatch-motion.css` | Gloss-language tokens, plates, stage, motion (scoped to `body.rl`) |
| `docs/rivalatch-motion.js` | Door loop beats + scroll settle; exports `BEATS` / `beatAt` for tests |
| `docs/assets/rivalatch-icon.jpg` | Gate mark (from vibegate brand) |
| `docs/assets/rivalatch-lockup.jpg` | Social / lockup |
| `tests/test_rivalatch_pages.py` | Static checks: links, no keys, demo labels, reduced motion |
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
