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
- IMU precursor: pad goes cyan and the strip reads `BODY -XXms` in the 5–80 ms window *before* the bit flips
- Receipt `.receipt.json` records clip-relative TEMPORAL binds (HID before the chapter mark)
- Deck replay shows the same ghosts and precursor over the source clip

## Ranking

Chapters at `t_s ≈ 0` (chat dumps, menus) are penalized. Score-change / clutch / confirm-score, coupling, input energy, and a HID press in the 400 ms TEMPORAL window before the mark win. A bodied press (`imu_precursor_ms`) ranks higher than a bare edge.

## Removed

The LTX / paid image-to-video path was removed. It did not fit a local observation plane.
