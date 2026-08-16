# Pages redesign notes — 2026 instrument site

Branch: `feat/pages-redesign-2026`  
Live today: https://conwan30.github.io/Qoresence/ (still the previous long-scroll until this lands on `main`).

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
