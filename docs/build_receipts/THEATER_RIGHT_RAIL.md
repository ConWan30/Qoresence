# Theater right rail — Receipt / AgentRail removal from LIVE page

Removes the Receipt plate (AgentRail component) from the Theater page right aside to fix clipping and honor viewport-law.

## Problem

The Theater LIVE right rail stacked SituationCard, ClutchFeed, ConnectCard, PadSyncCard, CouplingCard, and AgentRail (titled "Receipt") in an aside with `overflow-y-auto`. The Receipt box clipped, and the scrollbar did not show all content. This violated `viewport-law.test.ts` line 30: `theater-page.tsx must not contain overflow-y-auto` (no scrolling document).

## Decision

Qorector decided: Receipt / AgentRail is NOT needed on the LIVE right rail. Keep it only inside IntelligenceChamber. Actuator chips and last licensed agent line stay available when the operator opens the chamber drawer. Receipt data remains on `/health`.

## Changes

| Component | Before | After |
|---|---|---|
| `theater-page.tsx` | AgentRail imported + mounted in right aside (line 11, 53) | Removed import and mount. AgentRail stays in chamber only. |
| `theater-page.tsx` aside | `overflow-y-auto` on aside (line 47) | Removed. Aside is now `flex min-h-0` with no page scroll. |
| `intelligence-chamber.tsx` | AgentRail already mounted (line 55) | Unchanged. Receipt still lives here with proper `overflow-y-auto` on drawer content (line 52). |

## Remaining LIVE rail cards

The LIVE right aside now shows exactly five cards, fitting in `h-dvh` without clipping:

1. SituationCard
2. ClutchFeed (has its own internal `overflow-y-auto`)
3. ConnectCard
4. PadSyncCard
5. CouplingCard

Each card with internal scroll handles it inside the card component, not at the page level.

## Tests

- `glass/scripts/viewport-law.test.ts` — all pass (92/92)
  - `"viewport law: theater-page.tsx must not have overflow-y: auto on main"` — now compliant
  - `"viewport law: intelligence-chamber.tsx internal scroll only"` — unchanged, still correct

No other glass unit tests touched. All existing tests green.

## Hypothesis confirmed

The clip was AgentRail + `overflow-y-auto` on the aside fighting `h-dvh` `overflow-hidden`. Removing Receipt from the page and the aside scroll resolved the issue. Remaining cards fit without clipping.

## Where Receipt still lives

- **IntelligenceChamber drawer** (`glass/src/components/theater/intelligence-chamber.tsx` line 55) — Receipt mounts with proper overflow handling
- **`/health` endpoint** — Receipt data unchanged on the API
- **Component file** — `glass/src/components/theater/agent-rail.tsx` — not deleted, only unmounted from theater-page

## Branch and PR

- Branch: `cursor/glass-theater-receipt-rail-6ec9`
- PR: against `main` (not merged per operator instruction)
- Commit: `aa13a3a` — "fix(glass): remove Receipt (AgentRail) from Theater LIVE right rail"
