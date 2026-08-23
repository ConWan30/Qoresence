# Retina Monitor — native operator glass

Windows-first local window that blits **the same frames** Qoresence already holds from `StreamerRuntime`. **No second DShow open. No JPEG browser path.**

---

## Prerequisites

**Capture ownership:** prefer **Qoresence owns the physical card** (see [OBS_OWNS_CARD.md](OBS_OWNS_CARD.md)).  
Do not dual-open the same DShow device with OBS.

---

## Architecture

```text
StreamerRuntime ──push──► clip_buffer (Foundry / MJPEG / clips)
       │
       ├── get_current_frame() ──► Visual / OCR (existing)
       │
       └── FrameHub.publish(frame) ──► Retina Monitor window
                                          ├── OpenCV blit (no JPEG)
                                          └── optional situation strip (HTTP /api/situation)
```

**Invariants**

1. Monitor **subscribes** to frames already owned by Qoresence.  
2. Pattern A: frames come from OBS Virtual Camera inside streamer; monitor only displays.  
3. Pattern B: streamer owns physical card; monitor still only displays.  
4. Closing the monitor does **not** stop streamer, Deck, or ClutchBot.  
5. Default **OFF** — requires `--monitor`.

---

## Usage

```text
# Recommended — Qoresence owns physical card (OBS must not open that device)
python -m qoresence.cli --play --deck --monitor --streamer-device 0 --streamer-fps 60

# Legacy — OBS physical + Virtual Cam
python -m qoresence.cli --play --deck --monitor --streamer-device <OBS_VCAM> --streamer-fps 30
```

Optional display width:

```text
--monitor-max-width 1280
```

HUD layout presets (`--monitor-preset`):

| Preset | Shows |
|--------|-------|
| `minimal` | Frame only — no overlay bar |
| `situation` | Frame + situation strip (score, quarter, down) |
| `full` | Situation + controller + frame age/seq (default) |

Cycle presets live in the window with the **`p`** key.

Dependency (OpenCV HighGUI):

```text
pip install "qoresence[monitor]"
# or
pip install opencv-python
```

If `--monitor` is set and OpenCV is missing, play/Deck still start; monitor logs an install hint.

Standalone (only useful if FrameHub is already published in-process):

```text
python -m qoresence.monitor
```

Prefer the in-process `--monitor` flag.

---

## Latency expectations

| Glass | Expected lag vs TV |
|-------|---------------------|
| **Stem Program** (`--stem-program`) | Pattern B operator eye — FrameHub blit, optional fullscreen |
| **Retina Monitor** (`--monitor`) | Same FrameHub blit; windowed HUD |
| OBS Preview (physical card) | Pattern A only — do not dual-open the card |
| Deck LIVE `/video` JPEG | Ops preview only |

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Black / “waiting for FrameHub” | Streamer not running or wrong device; check `--streamer-list` |
| Window never opens | Install opencv; check log for monitor error |
| Esc / close window | Stops **only** monitor |
| Dual-open physical card | Close OBS Video Capture on that device; Pattern B owns physical index |

---

## Related

- [OBS_OWNS_CARD.md](OBS_OWNS_CARD.md) — capture ownership (Pattern B recommended)  
- [tools/obs/VIRTUAL_CAM.md](../tools/obs/VIRTUAL_CAM.md) — legacy Pattern A only  
