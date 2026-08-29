# Theater ClutchFeed SPA Vendor Update

Rebuilds and vendors the glass Vite app to sync qoresence/deck/glass_spa with the ClutchFeed-only theater layout.

## Problem

The LIVE Deck server serves the vendored SPA from `qoresence/deck/glass_spa`. After PR #107 landed the ClutchFeed-only theater layout in `glass/src/components/theater/theater-page.tsx`, the vendored SPA was stale. Operator Theater at `/deck.html` still painted the old scroll rail (Situation / hardware / scorebug stack with `overflow-y-auto`) because:

- Source of truth: `glass/src/components/theater/theater-page.tsx` has `h-dvh overflow-hidden` (NOT `overflow-y-auto`), mounts only `<ClutchFeed />` on right rail
- Vendored SPA: `qoresence/deck/glass_spa/assets/index-CnqMoCYT.js` still contained the old rail layout with `overflow-y-auto`

## Decision

Rebuild the glass Vite app and vendor the production dist into `qoresence/deck/glass_spa` to match current source.

## Changes

| File | Before | After |
|---|---|---|
| `qoresence/deck/glass_spa/index.html` | References `index-CnqMoCYT.js`, `index-DRXhFIAL.css` | References `index-BT7YTniF.js`, `index-BO9RGue-.css` |
| `qoresence/deck/glass_spa/assets/` | Old hashed JS/CSS (stale layout) | New hashed JS/CSS (ClutchFeed-only layout) |

## Build steps

```bash
cd glass
npm install
npm run build
rm -rf ../qoresence/deck/glass_spa/assets/*
cp -r dist/* ../qoresence/deck/glass_spa/
```

## Verification

1. ✓ `theater-page.tsx` still has `overflow-hidden` on main, mounts only `ClutchFeed` on right aside (lines 25, 42-44)
2. ✓ New `index.html` references new hashed assets (`index-BT7YTniF.js`, not `index-CnqMoCYT.js`)
3. ✓ `overflow-y-auto` in new bundle is from `ClutchFeed` component's own scroll (line 14 of `clutch-feed.tsx`), not from theater page container — expected and correct

## Context

This is a vendor-sync only — no layout changes. PR #107 already landed the ClutchFeed-only theater layout. This receipt documents rebuilding and vendoring the SPA so LIVE serves the current layout.

## Branch and PR

- Branch: `cursor/theater-clutchfeed-spa-7f81`
- PR: Against `main` (draft, not merged per operator instruction)
- Commit: rebuild and vendor glass SPA for ClutchFeed-only theater layout

## Plane affected

- Deck / Monitor (glass UI vendor only, no streamer/capture/HID changes)
