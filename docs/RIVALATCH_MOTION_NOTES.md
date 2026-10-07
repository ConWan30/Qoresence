# Rivalatch motion door — Qoresence Pages

Date: 2026-10-07 · Author: Grok Bot (Pages motion front end)

Live path (after merge): https://conwan30.github.io/Qoresence/rivalatch.html

## Intent

Add a Rivalatch-themed motion surface on the existing Qoresence GitHub Pages
hallway without inventing Spec fields, without embedding API keys, and without
claiming a live Ship session. Public name **Rivalatch**; wire identifiers stay
VibeGate.

## Motion

Same closed-form spring model as `docs/motion.js` (hallway hold loop from PR
#263 era): `seek(t)`, underdamped step, no CSS transitions, no audio, 120 BPM,
eight states, sixteen-second period. `prefers-reduced-motion` keeps the static
DOOR · HOLD frame.

| # | t | State | On the shape |
|---|---|---|---|
| 1 | 0s | Knock | Control: gate.run |
| 2 | 2s | Lodged | Loader + 202 · new key |
| 3 | 4s | held | First caller / story A |
| 4 | 6s | Replay | Same key · same payload |
| 5 | 8s | Recalled | 200 · idempotent |
| 6 | 10s | Rival | Same key · different payload |
| 7 | 12s | Contested | 409 · held \| incoming lanes |
| 8 | 14s | Return | Morphs back to Knock |

Prose tags only. HTTP numbers are the frozen door (`202` / `200` / `409`).
No GateResult / OpenAPI / MCP tool invention.

## Files

| Path | Job |
|---|---|
| `docs/rivalatch.html` | Door hallway page + CTAs |
| `docs/rivalatch-motion.css` | Door stage (flat void / iron) |
| `docs/rivalatch-motion.js` | Door loop `seek(t)` |
| `docs/assets/rivalatch-icon.jpg` | Gate mark (from vibegate brand) |
| `docs/assets/rivalatch-lockup.jpg` | Social / lockup |
| `docs/index.html` (+ other Pages) | Nav + home CTA + footer link |
| `docs/RIVALATCH_MOTION_NOTES.md` | This note |

## CTAs (public only)

- Door: https://vibegate-production.up.railway.app
- Door board: https://vibegate-production.up.railway.app/door/
- MOBILE_KNOCKER: https://vibegate-production.up.railway.app/MOBILE_KNOCKER.md
- Listing: https://vibegate-production.up.railway.app/listing/
- AGENT.md: https://vibegate-production.up.railway.app/AGENT.md

Auth is named (`X-Api-Key`) but never valued on Pages.

## Non-goals

- Spec / OpenAPI / GateResult changes
- Secrets, challenge tokens, or example API keys in HTML/JS
- X posts or merge-to-main without operator Proceed
- Claiming this page is a live knock surface (it is a door loop + outbound links)
