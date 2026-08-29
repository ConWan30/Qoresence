# Theater PadSync card text clipping fix

Fixes horizontal text clipping in PadSyncCard on the Theater LIVE right rail by ensuring text wraps properly within the constrained aside width.

## Problem

After PR #106 removed `overflow-y-auto` from theater-page.tsx aside (for viewport-law compliance), the PadSyncCard text content was clipping horizontally. The pad-wake instruction "wake the pad — USB to this laptop, then press R2" was cut off at "USB TO" with no scrollbar, visible especially in narrower Edge windows.

The aside is constrained to `min-w-[18rem] max-w-[21rem]` (line 46 of theater-page.tsx), and without `overflow-y-auto`, long text that didn't wrap would clip at the container edge.

## Root cause

PadSyncCard text paragraphs and grid cells lacked explicit wrapping directives. With the aside having no overflow scroll (removed by PR #106 for viewport-law compliance), content that exceeded the container width would clip horizontally rather than wrap to the next line.

## Changes

| Component | Before | After |
|---|---|---|
| `pad-sync-card.tsx` line 65 | Main "why" text: no wrap control | Added `break-words` to allow wrapping |
| `pad-sync-card.tsx` line 69 | Metadata text: no wrap control | Added `break-words` to allow wrapping |
| `pad-sync-card.tsx` line 83-96 | Grid cells: no overflow handling | Added `truncate` to each span for graceful overflow |
| `pad-sync-card.tsx` line 99 | Held buttons text: no wrap control | Added `break-words` to allow wrapping |
| `pad-sync-card.tsx` line 103 | Pad-wake instruction: no wrap control | Added `break-words` to allow wrapping |

## Solution approach

Applied `break-words` to all text paragraphs (`<p>` elements) and `truncate` to grid cells (`<span>` elements within the grid):

- **Text paragraphs**: `break-words` allows long words and text to wrap mid-word if necessary, ensuring the full content is visible within the container width
- **Grid cells**: `truncate` adds ellipsis (`...`) for content that overflows, maintaining the 2-column grid layout without horizontal overflow

This approach honors viewport-law.test.ts by not adding `overflow-y-auto` to theater-page.tsx, while ensuring all text content is accessible without horizontal clipping.

## Tests

- `glass/scripts/viewport-law.test.ts` — all pass (92/92)
  - `"viewport law: theater-page.tsx must not have overflow-y: auto on main"` — still compliant (no `overflow-y-auto` added)
  - No other viewport law tests affected

## Visual verification

The pad-wake instruction now displays fully as:
```
wake the pad — USB to
this laptop, then press R2
```

instead of clipping at "USB TO".

All PadSync card text content (situation "why" text, metadata, grid cells, and instructions) wraps or truncates gracefully within the 18-21rem aside width.

## Branch and PR

- Branch: `cursor/fix-theater-pad-wake-clip-657a`
- PR: #107 against `main` (draft, not merged per operator instruction)
- Commit: `840c9cb` — "fix(glass): prevent PadSync card text clipping in Theater LIVE rail"

## Plane affected

- Deck / Monitor (glass UI only, no streamer/capture/HID changes)
