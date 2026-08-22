# Phosphor Shell §1 — Glance Glyph + Lockbug Strip + Down Pill

Observation-plane chrome on Retina Deck Theater (Clock Glass / Retina Core only).

## Landed

1. **Glance Glyph** (`glass/src/components/theater/glance-glyph.tsx`) — F·C·L·P ice `#4FE0D4` solid when on; text-subtle hollow/40% when off. `data-frame|couple|lock|plane="on|off"`. Mobile/Lens compact = F·L only. Fail-closed when `!sameSeq` / `plane_dim` / `!paint`. SYNC trail ice `SYNC {syncLagMs}ms` (never forced 0).
2. **Lockbug Strip** (`lockbug-strip.tsx`) — unlocked `□–□ · — & —`; licensed `home–away · down & distance` only when widgets ok + board lock. Never paints unlocked OCR while dark.
3. **Down Pill** (`down-pill.tsx`) — unlocked `— & —` muted; locked e.g. `3rd & 7` lime `#C6F26A` when ticket-coupled lock ok.
4. **board.ts** — `downDistanceLabel`. **store.ts** — raw `homeScore`/`awayScore`/`down`/`distance`/`boardLocked` for fail-closed UI.
5. Fixture: `glass/fixtures/phosphor-shell-s1.json`. Soft collision CLEAR: lens chip stays lowercase `c` for coupling.

## Wire

- `lens-overlay.tsx` — Glyph + Lockbug + Down Pill on LIVE stage (`/live.jpg` only via hdmi-stage).
- `command-bar.tsx` — Lockbug in chrome; no unlocked confirm-pair fallback.

## Out of scope

Clutch Ring, Seq License, moment genetics, keep-last rewrite, Rail resurrection, MJPEG-as-img, invent scores, secrets, dual-open, authorship. Amber=fast / lime=confirm clutch semantics → Qoreglass later.

## Done when

Glyph + strip + pill on `/deck.html`; paint gates honored; hygiene markers (`score_vlm_locked`, `boardLocked`) survive vite+vendor.
