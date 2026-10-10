# Deck motion notes — Aperture Glass for the live deck (2026-10-09)

The operator deck (`qoresence/deck/`) now uses the same Aperture Glass language as the
Pages site (`docs/aperture.css`, `docs/PAGES_MOTION_NOTES.md`, PR #274). The Pages site
is a brochure. The deck is a live instrument, so the rules below put the HDMI picture
first and show only what the backend reports.

Front-end only. No server route, JSON shape, WebSocket/SSE/WebRTC contract, capture,
vision, ledger or fail-closed rule changed. Element ids and `data-*` hooks that JS or
tests read are unchanged.

## Where the styles live

| Surface | Served from | Styled in |
| --- | --- | --- |
| Theater `/deck.html`, `/index.html` | glass SPA | `glass/src/styles.css` + components |
| Session `/session.html` (`/civif.html` → 307) | glass SPA | same |
| Foundry `/studio.html`, Mobile `/mobile.html`, Lens `/overlay.html` | glass SPA | same |
| Observations `/observations.html` | standalone | inline `<style>` |
| OBS picture `/obs-live.html` | standalone | inline `<style>` |
| Clip dock (injected into SPA pages) | `clip-dock.css` / `clip-dock.js` | `clip-dock.css` |
| Knock Rivalatch pill (mobile) | `rivalatch-knock.js` | inline style strings |
| Lease lamp (deck, opt-in) | `lease_lamp.js` | injected `<style>` string |
| Fallback pages if `glass_spa/` is missing | `deck.html`, `studio.html`, `mobile.html`, `session.html`, `civif.html`, `overlay.html`, `session.css` | palette swap + same tab bar |

`qoresence/deck/glass_spa/` is a build artifact. Change `glass/src`, then run
`cd glass && npm ci && npm run build` and `python scripts/vendor_glass_spa.py`.
Never hand-edit the minified bundle. `scripts/check_glass_spa.py` still gates its size
(CSS < 64 KB, which is ~57 KB now).

## Tokens

The tokens are the Pages palette sampled from the logo, declared in `glass/src/styles.css`
`@theme` as `--color-void`, `--color-navy`, `--color-aqua`, `--color-aqua-hi`,
`--color-aqua-deep`, `--color-aqua-glow`, `--color-gold`, `--color-ink`,
`--color-ink-2`, `--color-mute`, `--color-blank`, `--color-plate`, `--color-line` and
`--color-line-hi`. The legacy names (`bg`, `surface`, `fg`, `live`, `sync`, `fast`,
`muted-foreground`, …) are remapped onto them, so existing utility classes keep working.

- **Gold `#fcde74` is for locked/confirmed only.** It is used on the licensed board
  digits (`LockbugStrip`, read board `.is-locked`), the open iris pins and tick, and the
  licensed OBS pill (`#pill[data-digit-integrity="licensed"]`). The old "brass" warning
  tone is now `ink-2 #b9cdd2`.
- `veto #e8877c` marks faults only: STALL, PLL loss and the reader error.
- Display type is a local serif stack (`Iowan Old Style`, `Palatino`, Georgia). Labels
  are tracked uppercase Instrument Sans or IBM Plex Mono, both self-hosted woff2. No
  CDN fonts: the deck runs offline.

## Glass plates

`.holo-header` and `.holo-plate` are 1px hairline plates (`rgba(169,251,253,.1)`) on
`plate`. `backdrop-filter` is used only inside `@supports`. The fallback is an opaque
plate, so text stays readable without blur. Nothing with blur, a tint or a filter ever
sits over the video: `.hdmi-picture` sets `filter: none`. The bezel
(`.holo-plinth`) sits around the picture well, with corner brackets drawn outside the
picture.

## The picture is the hero

- Theater: the picture fills the left column. The rail (read board, Foundry,
  play-by-play) sits beside it at ≥761px and below it on phones.
- Mobile: `/mobile.html` now mounts the stage as the clean `observatory` variant. No
  LensOverlay chips or phrase are painted on the picture. The same facts are shown in
  the meter strip above.
- The stage is a flex column, so the ISO clip dock under the picture is visible again.
  It used to be clipped below the well.
- `/overlay.html` (OBS lens) stays transparent. `html.obs-lens` forces
  `background: transparent` on html, body and `#root`, and keeps
  `color-scheme: normal`, because a dark color scheme makes Chromium paint an opaque
  canvas. The baseline SPA overlay painted the void colour; the checkerboard shots show
  it is transparent now.

## Tally (LIVE / HOLD / STALL / DARK)

`tallyState()` in `glass/src/lib/coupling/signal-meter.ts` reads `/health` only:

| State | Rule |
| --- | --- |
| DARK | `/health` older than 4 s, no frame, or no `video.age_s` |
| STALL | `age_s > 5 s`, or the frame counter (`pushes`) stopped advancing |
| LIVE | `paint` true, `same_seq` not false, plane not dim, `age_s ≤ 1 s` |
| HOLD | anything else (and always while REPLAY is on stage) |

The old tally used the front-end capture status and could read "ON AIR" with no
capture. LIVE now only lights when the backend says the picture is painting.

## Signal meters

The meter strip under the tabs is a broadcast meter bridge, one cell per backend
field:

- Card: `lease.device`, plus a lease note.
- Frames++: Δ`video.pushes`/s, falling back to `frames` (`frames` plateaus at the
  ClipBuffer capacity).
- Age: `video.age_s`, with a 5-segment bar.
- FPS: `sync_health.fps_meas` / `target_fps`.
- PLL: lock or open.
- Same seq: `video.same_seq`.
- Paint: `paint` and `paint_reason`.
- Join, Pad, Deck, and the local clock.

Each cell has a 2px tone rule: `ok` aqua, `hold` mute, `dark` line, `fault` veto.

## Read board and read ticks

The read board (`situation-card.tsx`) shows:

- the iris, open only when the board is licensed (ConfirmTicket + `score_vlm_locked` +
  fresh ticket, via `pickBoard`);
- gold digits only when locked, and blank cells otherwise;
- the `local_scorebug` block: reads, agreed, disagreements, and the last blank reason.

The ticks only claim what `/health.local_scorebug` reports. The backend gives
`state` (`sure`/`blank`) and `reason`, but not the run length. So:

| Backend | Ticks |
| --- | --- |
| `state: "sure"` | 3/3, LOCKED (gold) |
| `reason: "agreeing"` | 1 lit, "agreeing ≥1/3" |
| `reason: "recheck"` | 1 lit of 9, "recheck ≥1/9" |
| anything else | 0/3 with the reason, DARK (blank cells) |
| reader off / error | 0/3, dark |

Partial counts (2/3) are never invented.

## Goes dark instead of lying

`ApertureIdent` is the honest empty frame. It shows a dashed safe area, the closed
iris, a serif italic "Dark" and "No picture shown · {paint_reason}". There are no
spinners and no placeholder art.

## Motion

- Only `transform` and `opacity` animate. That covers the iris blades and ring, the
  tick-in, the feed rows landing and the lockbug lock.
- Hover and press use color and border transitions only.
- No constant animation on the OBS pages. `overlay.html` and `obs-live.html` lost their
  `backdrop-filter` blur; their plates are slightly more opaque instead.
- `prefers-reduced-motion: reduce` turns off the keyframes and the iris transitions.
  The state is still shown, statically.
- Easing is `cubic-bezier(.2,.7,.1,1)`, the same curve as Pages.

## Tab bar

The tab bar is one pill bar on every surface: SPA `.glass-nav`, `session.css`, the
inline styles in fallback `deck.html` and `studio.html`, and the observations nav. The
current tab is an aqua outline, not a fill, so it can't be mistaken for the LIVE tally.
The gamer routes keep only Theater and Session (`GAMER_GLASSES`).

## Verification fixture

The box that built this has no capture card. The screenshots in the PR used a fixture:
a 1280×720 still cropped from `docs/assets/deck-live-demo.jpg`, served as `/live.jpg`
and `/video`, plus patched `/health` and `/api/situation` JSON. The "dark" shots
intercept nothing: they are the real server with no capture. Live capture on the
Windows laptop, WebRTC and OBS's CEF were not exercised.
