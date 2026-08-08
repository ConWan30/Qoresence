---
title: "Novel stack: FrameHub, IVC, Qoresence-owns-card, one brain N glasses"
category: Announcements
---

# Novel stack (milestone discussion)

## Shipped on main

### Qoresence owns the card (Pattern B recommended)
Physical HDMI → Qoresence StreamerRuntime. OBS (optional) uses Browser Source for Lens + game/display capture — not dual-open DShow. Pattern A VCam is legacy.  
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
python -m qoresence.cli --play --deck --monitor --controller --streamer-device 0 --streamer-fps 60
```

Feedback on DualSense Edge decode noise and OCR scorebug stability is especially useful.
