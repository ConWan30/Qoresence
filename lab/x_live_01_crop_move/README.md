# LAB / FIXTURE — X LIVE 0-1 crop_hash move silence

**NON-CLAIM. Spike/lab only. Do not merge as product. Do not ride `--play`.**

Proves the X LIVE claim ceiling after [#152](https://github.com/ConWan30/Qoresence/pull/152) (`374e940` pickBoard gate) and [#153](https://github.com/ConWan30/Qoresence/pull/153) (`7a7393f` docs):

When confirm is stuck at `home=0 away=1` (or `last_confirm` 0-1) **and** FrameHub `crop_hash` moves to a new board, shared `pickBoard` / overlay digits must **EMPTY**. Blank beats hold. Never paint last-good.

`0-1` is a licensed lock when the crop still matches (not the `0-0` refuse). The move is what silences.

Shared-wire silence (`stuck_01_crop_moved_silence`): situation + video `crop_hash` both move → `pickBoard` and overlay digits EMPTY.

FrameHub-only bag (`stuck_01_framehub_video_only_pickboard`): `video.crop_hash` moves while situation still holds last-good 0-1. `pickBoard` empties. overlay.html reads situation `crop_hash` only — recorded as observation, not a product fix.

## Out of scope

`--play` · DualSense · `--x-glass` · encoder · WHIP · RTMP · secrets · force-push `main`

## Shared gate

- `glass/src/lib/coupling/board.ts` — `ticketFresh` / `digitsLicensed` / `pickBoard`
- `docs/X_LIVE_STUDIO.md` — ConfirmTicket + `score_vlm_locked` + ticket-fresh
- `qoresence/deck/overlay.html` — fallback `digitsLicensed` (situation `crop_hash`)

## Run

```powershell
node lab/x_live_01_crop_move/harness.mjs
python lab/x_live_01_crop_move/harness.py
python -m pytest tests/test_x_live_01_crop_move_silence.py -v
```

CI Node is 20. `harness.mjs` is plain JS (no `board.ts` import, no `--experimental-strip-types`). Glass `pickBoard` stays in `glass/scripts/x-live-01-crop-move.test.ts` (Node 22+ local).
