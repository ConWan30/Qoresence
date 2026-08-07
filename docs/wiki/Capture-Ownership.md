# Capture ownership

## Rule

**One physical DirectShow capture device has one owner.**

| Pattern | Physical card | Qoresence streamer | When |
|---------|---------------|--------------------|------|
| **A (recommended)** | OBS | OBS Virtual Camera index | Daily streaming |
| **B (lab)** | Qoresence | Physical index | OBS must not open that device |

## Why

Dual-open causes black frames, thrash, and failed starts. OBS Preview is the low-lag eye on Pattern A; Qoresence is situation, clips, ClutchBot, IVC.

Full doc: [docs/OBS_OWNS_CARD.md](https://github.com/ConWan30/Qoresence/blob/main/docs/OBS_OWNS_CARD.md)
