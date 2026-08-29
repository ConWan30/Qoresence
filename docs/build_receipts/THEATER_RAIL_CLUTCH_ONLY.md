# Theater LIVE rail — ClutchFeed only

Simplifies the Theater LIVE right rail to show only ClutchFeed, moving all situation/hardware/scorebug cards to IntelligenceChamber.

## Problem

The Theater LIVE right rail stacked five cards (SituationCard, ClutchFeed, ConnectCard, PadSyncCard, CouplingCard) in the 18-21rem aside. On narrow viewports, cards clipped below the fold. The operator (ConWan30) requested: "delete the other boxes — Situation, scorebug, and hardware — leaving ClutchFeed."

## Decision

The LIVE rail shows ONLY ClutchFeed. All other cards (situation, hardware: Connect/PadSync/Coupling) move to IntelligenceChamber drawer where they remain accessible. LockbugStrip (scorebug on stage) stays on the HDMI picture — it is not a "box" on the rail.

## Changes

| Component | Before | After |
|---|---|---|
| `theater-page.tsx` imports | SituationCard, ClutchFeed, ConnectCard, PadSyncCard, CouplingCard | ClutchFeed only |
| `theater-page.tsx` aside (line 42-44) | Five card mounts | ClutchFeed only |
| `intelligence-chamber.tsx` | Already has all cards (lines 54-60) | Unchanged — cards still accessible in drawer |
| `observatory-hud.tsx` / `hdmi-stage.tsx` | LockbugStrip on stage | Unchanged — scorebug stays fail-closed on picture |

## Rail contents

### Theater LIVE right rail (page-level)

- **ClutchFeed** — moment chips, auto-clip status, clutch pulse

### IntelligenceChamber drawer (accessible via "Intel" toggle)

All removed cards remain available when operator opens the drawer:
- HighlightDirector
- AgentRail (Receipt)
- ClutchFeed (duplicate for chamber)
- ConnectCard (hardware)
- PadSyncCard (hardware)
- SituationCard (scorebug data)
- CouplingCard (hardware)

## Scorebug clarification

**LockbugStrip** (the scorebug overlay on the HDMI picture) was NOT removed. It stays on the stage showing fail-closed □–□ until a seeing-path ticket licenses score digits. "Delete the scorebug" meant the **SituationCard box on the rail**, not the licensed lockbug overlay on the picture.

## Tests

- `glass/scripts/viewport-law.test.ts` — all pass (92/92)
  - `"viewport law: theater-page.tsx must not have overflow-y: auto on main"` — still compliant
  - No `overflow-y-auto` added

## Hypothesis confirmed

The fold hid PadSyncCard and other cards because the aside stacked five cards in limited vertical space. With only ClutchFeed, the single card fits comfortably without clipping or requiring scroll.

## Branch and PR

- Branch: `cursor/fix-theater-pad-wake-clip-657a` (same branch, updated)
- PR: #107 against `main` (draft, not merged per operator instruction)
- Commit: simplify Theater LIVE rail to ClutchFeed only

## Plane affected

- Deck / Monitor (glass UI only, no streamer/capture/HID changes)
