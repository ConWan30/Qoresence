---
title: "Novel stack: FrameHub, IVC, OBS-owns-card, one brain N glasses"
category: Announcements
---

# Novel stack (milestone discussion)

## Shipped on main

### OBS owns the card (Pattern A)
Physical HDMI stays in OBS. Qoresence opens **Virtual Camera** only.  
Doc: `docs/OBS_OWNS_CARD.md`

### FrameHub + Retina Monitor
Streamer publishes frames it already holds. `--monitor` blits via OpenCV — **no second DShow open**.  
Doc: `docs/RETINA_MONITOR.md`

### Input–Video Coupler
`InputRing` + IVC join DualSense edges to `frame_seq` / `clock_ns` for **coupling** scores, clip `*.buttons.json` sidecars, and thin moment boost.  
Doc: `docs/CONTROLLER_VIDEO_SYNC.md`

### Retina Deck
Local Lens + Ghost Theater + LIVE MJPEG + Foundry export API.  
`--play --deck` is the daily pilot.

## Why this is different

Most “game bots” either scrape cloud APIs or open the same capture card twice. Qoresence is **local-first**, **multi-glass**, and **clock-joined** without truth-plane claims.

## Try it

```text
python -m qoresence.cli --play --deck --monitor --controller --streamer-device <OBS_VCAM> --streamer-fps 30
```

Feedback on lag bands (VCam) and DualSense Edge decode noise is especially useful.
