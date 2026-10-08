# Capture ownership

## Rule

**One physical DirectShow capture device has one owner, and that owner is Qoresence.** OBS never opens the card; it only gets the overlay as a Browser Source (`http://127.0.0.1:8765/overlay.html`).

| Setup | Physical card | Qoresence streamer | When |
|-------|---------------|--------------------|------|
| **Current (Pattern B)** | **Qoresence** | Physical index (e.g. `USB3.0 Video` = 0) | Every session |
| Legacy Pattern A | OBS | OBS Virtual Camera index | Not recommended; kept for reference only |

## Why

Dual-open causes black frames, thrash, and failed starts. Qoresence owns the card for full-rate OCR, FrameHub, Monitor, and IVC. OBS (optional) uses Browser Source for Lens and game/display capture for RTMP — not the same DShow device.

Full doc (old file name; it describes the Qoresence-owns-the-card setup): [docs/OBS_OWNS_CARD.md](https://github.com/ConWan30/Qoresence/blob/main/docs/OBS_OWNS_CARD.md)
