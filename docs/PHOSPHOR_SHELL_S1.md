# Phosphor Shell §1 — Glance Glyph + Lockbug Strip + Down Pill

Shell-only placeholder until implement fills Theater.

## Intent

Phosphor Shell §1 lands three observation-plane chrome pieces on Retina Deck Theater:

1. **Glance Glyph** — compact presence / lock affordance on the LIVE stage.
2. **Lockbug Strip** — scoreboard / VLM lock strip that honors Same-Seq + Dark Theater paint gates.
3. **Down Pill** — down-and-distance (or sport-equivalent) pill tied to locked board optics.

## Scope (implement later; not this PR's commits yet)

- `glass/src` Theater components (glyph, strip, pill) wired into the existing stage / situation chrome.
- `glass/src/lib/coupling/board.ts` (and store ingest as needed) for any strip/pill fields from Deck snapshot.
- Docs/allowlist updates OK in this shell track.

## Out of scope

- No new capture owner. No dual-open of the card.
- No invented scores. No QorTroller / PoAC / *-truth.
- Not Clutch Ring / Ghost Stick / full Phosphor Shell beyond §1.
- Optional lobes stay OFF unless already on main.

## Done when (for the implementer)

- Glance Glyph, Lockbug Strip, and Down Pill render on `/deck.html` (and related Theater surfaces as designed).
- Paint honors `paint_reason=ok` + Same-Seq; veto on `seq_skew` / `not_play` / `no_frame` / plane dim.
- Tests + RETINA_DECK_UIUX notes for §1.

## Status

**Shell only.** Placeholder doc. Implement fills glass Theater + board.ts on this branch.