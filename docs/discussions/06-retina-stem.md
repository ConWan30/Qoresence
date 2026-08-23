---
title: "Retina Stem — situation-directed program, not OBS"
category: Announcements
---

# Retina Stem

Qoresence can now run a local match **without OBS Preview**.

**Retina Stem** is one timeline with grouped tracks: HDMI + (optional) capture-card audio + DualSense + situation chapters, all on `clock_ns`. Foundry cuts from the Stem. Deck and Monitor look at the Stem. The Conductor publishes `watch / prime / armed / hold / encode` — it does **not** switch OBS scenes.

### What shipped

- Conductor rides `--play` and emits `stem_program` on the bus and `/retina`
- `--stem-program` promotes Retina Monitor to Program-out (second display, optional HUD burn-in). FrameHub stays clean for OCR/VLM
- `--stem-audio` is capture-card audio only — laptop mics stay closed
- `--stem-record` is opt-in session mux to `clips/stem_*.mp4` (not a 1.0 gate)

### Pilot order (do not invert)

1. Card in. Capture health (`age_s < 1`, frames climbing). Score lock. One local HDMI clip.
2. Then `--stem-program` so OBS is unused for **ops**.
3. Audio and Record after LIVE is healthy.

```powershell
python -m qoresence.cli --play --deck --stem-program --streamer-fps 60
```

- **Discussion:** https://github.com/ConWan30/Qoresence/discussions/48
- **Wiki:** https://github.com/ConWan30/Qoresence/wiki/Retina-Stem

Docs: [STEM.md](https://github.com/ConWan30/Qoresence/blob/main/docs/STEM.md) · [Wiki](https://github.com/ConWan30/Qoresence/wiki/Retina-Stem)

No stream ingest. No Twitch. No Virtual Cam. OBS remains optional only if you still want a platform stream — that is a different product.
