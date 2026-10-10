# Pages motion notes — Aperture Glass, logo palette (2026-10-09)

Live site: https://conwan30.github.io/Qoresence/ (source: `docs/`).
Supersedes the token table and loops in `PAGES_REDESIGN_NOTES.md` (kept for history).

Structure, polish and motion follow the Rivalatch site
(https://vibegate-production.up.railway.app/): near-black backdrop, serif display
headline with an italic second line, small tracked uppercase labels, glass plates
with hairline edges, inline SVG state glyphs, one animated demo stage, a state
legend. Colors come from the Qoresence HDMI-Q logo instead of Rivalatch gold.

Every `docs/*.html` page links one stylesheet (`docs/aperture.css`) and one script
(`docs/site.js`). No page carries a `<style>` block. `trace.html` keeps its inline
viewer script.

## Palette (sampled from `docs/assets/qoresence-logo.png`)

Sampled with Pillow: the median of each pixel class in the 1024×1024 logo.

| Token | Hex | Where it comes from | Use |
| --- | --- | --- | --- |
| `--void` | `#010206` | logo background | page backdrop |
| `--navy` | `#011c24` | halo just outside the ring | backdrop wash, stage well |
| `--aqua` | `#66e0e6` | line art, median | the one accent: kickers, links, primary button, reading |
| `--aqua-hi` | `#a9fbfd` | brightest ring highlight | iris ring when open, recheck, scan line |
| `--aqua-deep` | `#3f979b` | inner, dimmer strokes | plate rules, blade edges |
| `--aqua-glow` | `#1c5859` | glow falloff | backdrop light only |
| `--gold` | `#fcde74` | the tick + HDMI pins | **locked only**: locked board, seal pin, iris pins and tick |

Built on the samples: `--plate #08131a`, `--line #16262e`, `--line-hi #24414a`,
`--ink #e4f1f3` (headings), `--ink-2 #b9cdd2` (lede, body in essays), `--mute #8a9ea6`
(slate body copy, 6.7:1 on the plate), `--faint #566a72` (decoration only, never body
text), `--blank #0d1a21` (dark blanks: empty read cells).

Glow is used sparingly: the header mark, the iris ring, the scan line and the CTA mark.
No glow on text.

Gold appears only on lock selectors (`.q-board.is-locked`, `.q-iris.is-open`,
`.q-seal`, `--st-locked`). `tests/test_rivalatch_pages.py` checks that, and checks
the tokens against the logo pixels when Pillow is installed.

Type: serif display (system Iowan / Palatino / Georgia stack, no download), Instrument
Sans for body and labels, IBM Plex Mono for wire values. Both are self-hosted in
`docs/fonts/` with their OFL licenses. No CDNs, no external requests.

## Board states and glyphs

Inline SVG data-URI masks (`--g-*`, 16×16), tinted with `currentColor`. The shape
alone carries the meaning, so the legend reads in grayscale.

| State | Tone | Glyph | Meaning |
| --- | --- | --- | --- |
| Signal | `--aqua` | HDMI port outline | a capture frame came in |
| Reading | `--aqua` (rule `--aqua-deep`) | dashed ring + core (slow turn) | 1/3, 2/3, 3/3 matching reads |
| Locked | `--gold` | open aperture (hexagon in a ring, six blades) | three matching reads; board shows score/clock/quarter |
| Dark | `--mute` | empty square □ | banner, replay, menu or doubtful frame: blank, not last-good |
| Recheck | `--aqua-hi`, dashed plate | circular arrow | suspicious jump: needs 9 reads over 2 s |

Plates carry a 2px margin rule in their tone. Recheck plates use a dashed edge.

## Hero demo: the read stage (`[data-read-stage]` on `index.html`)

Labelled **"Demo · fixture frames · not live"**. `site.js` only swaps classes and text
on a timer; it makes no network calls. The scorebug is a Madden-style strip drawn in
HTML/CSS (team names are not read, so it says Away / Home). Fixture values avoid the
digit 8 and clocks of 10:00+, which the local reader does not know yet.

One 16 s loop:

| t (ms) | Beat | Board | Iris |
| --- | --- | --- | --- |
| 0 | dark | □ – □, 0/3 | closed |
| 1000 / 2000 / 3000 | read 1/3, 2/3, 3/3 (14 · 10 · 2nd · 3:12 → 3:10) | □ – □, reading | closed |
| 3700 | **locked** | gold 14 – 10 · 2nd · 3:10, 3/3, seal | opens |
| 7600 | doubt: REPLAY banner slides over the scorebug | □ – □, dark | closes |
| 10400 | recheck: 14–10 → 14–14 is not a football step | □ – □, 0/9 | closed |
| 10900–12100 | recheck 1/9 … 4/9 | □ – □ | closed |
| 12700 | blank read resets the run | □ – □, still dark | closed |
| 14900 | fade, then loop | | |

Digits reach the board only on the locked beat (tested). The facts behind the beats:
3 sampled frames ≥200 ms apart spanning ≥400 ms; a blank, a different read, a gap,
or a clock running backwards resets the run; a suspicious jump (a drop, both sides
moving, a non-football step) needs 9 reads over 2 s; banners/replays blank. See the
local scorebug reader (PR #271) and `install.html#scores`.

The aperture is an inline SVG: six filled blades plus six edge strokes over the HDMI
port and its nine pins, clipped to the ring. Opening = each blade translates outward
along its own axis and the blade group turns 24°; the pins and the top tick turn gold.

## Motion rules

- Animations are `transform` / `opacity` only (plate settle, board seal, stamp, read
  ticks, scan line, signal pulse, banner slide, iris blades, glyph turn, CTA rings,
  backdrop drift). Small color transitions on state change. A test reads every
  `@keyframes` block and fails on any other property.
- One easing curve: `cubic-bezier(0.2, 0.7, 0.1, 1)`; hover 160 ms, settle 620 ms,
  draw (iris, seal) 900 ms.
- `prefers-reduced-motion: reduce`: every animation and transition off; the stage shows
  one settled frame, **LOCKED**. Plates are visible immediately.
- No JS: the markup is that same settled LOCKED frame and nothing starts hidden.
  Reveal and shutter only hide content under `html.q-motion`, which the script adds.
- Hidden tab: `visibilitychange` clears the stage timers and sets `html.is-tab-hidden`,
  which pauses every CSS loop on the page. The loop restarts from the top when visible.
- Plates settle in once on scroll (70 ms stagger), then hand back to normal styles.
  The tape plinth shutters open once.

## Fallbacks

- Glass plates use `backdrop-filter: blur(18px)` inside `@supports`; without it they
  are opaque (`--plate #08131a`), so contrast never depends on blur. Same for the header.
- Header: sticky glass bar above 680px. At 680px and below it scrolls away and the nav
  stays visible as one swipeable row under the wordmark (edge mask, no scrollbar, no
  page overflow); the current page is scrolled into view. There is no menu button.
- Anchor jumps clear the sticky header (`scroll-padding-top`, kept in sync by
  `site.js`).

## Pages

| Page | What changed |
| --- | --- |
| `index.html` | New hero: serif headline + read stage; opener facts under it; board-state legend (`#states`); `#watch` is now "Sure, or blank." with six read rules; tape, proof, Rivalatch receipt band (`#receipt`), CTA (`#next`). |
| `watch.html`, `install.html`, `limits.html` | New header; serif h1 with italic second line; content, anchors and copy buttons unchanged. |
| `dark.html` | New header; essay in one glass plate with tracked section labels. |
| `trace.html` | New header; viewer restyled; inline viewer script unchanged. |
| `rivalatch.html` | New header; pointer card restyled (aqua rule, gold kept for lock). |

Retired with this change: the menu button (`data-menu`), the Hold loop and the unused
door loop in `site.js`, and the old `--bg/--fg/--live/--fast/--veto/--st-*` tokens.
