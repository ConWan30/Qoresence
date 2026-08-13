# Foundry Bay — Ghost Cut

Foundry Bay is Qoresence Studio. **Ghost Cut** edits a local HDMI clip and burns the chapter, score, and *timed controller ghosts* onto the picture. There is no generative video API and no paid model.

Default-off. Post-session. Never on the live event bus.

## Why this exists

Qoresence is the only local plane that has HDMI + DualSense on one clock. Ghost Cut is that fact made visible: the press and the play on the same frame.

## Operator

```powershell
python -m qoresence.cli --play --deck --studio --streamer-device 0 --streamer-fps 30
# http://127.0.0.1:8765/studio.html  →  Cut highlight
```

One-shot after a session:

```powershell
python -m qoresence.cli --foundry-reel --foundry-reel-count 1
```

Output: `clips/<stem>_cut/reel_<id>.mp4` plus `.receipt.json`.

## What it burns

- Why strip: kind, score, chapter label
- Clock tick across the cut window
- DualSense ghost pad: face + shoulder buttons light when that press is live in `*.buttons.json`
- Deck replay shows the same ghosts over the source clip

## Ranking

Chapters at `t_s ≈ 0` (chat dumps, menus) are penalized. Score-change / clutch / confirm-score and coupling + input energy win.

## Removed

The LTX / paid image-to-video path was removed. It did not fit a local observation plane.
