# Capture ownership

## Rule

**One physical DirectShow capture device has one owner.**

| Pattern | Physical card | Qoresence streamer | When |
|---------|---------------|--------------------|------|
| **B (recommended)** | **Qoresence** | Physical index (e.g. `USB3.0 Video` = 0) | Daily pilot going forward |
| **A (legacy)** | OBS | OBS Virtual Camera index | Only if you still need OBS Preview on the card |

## Why

Dual-open causes black frames, thrash, and failed starts. Qoresence owns the card for full-rate OCR, FrameHub, Monitor, and IVC. OBS (optional) uses Browser Source for Lens and game/display capture for RTMP — not the same DShow device.

Full doc: [docs/OBS_OWNS_CARD.md](https://github.com/ConWan30/Qoresence/blob/main/docs/OBS_OWNS_CARD.md)
