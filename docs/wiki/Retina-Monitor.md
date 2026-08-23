# Retina Monitor

A native OpenCV window that shows the same frames Qoresence already holds. **No second DShow open. No JPEG browser path.**

## Why it exists

- Lower latency than Deck MJPEG.
- No need for a browser.
- Subscribes to `FrameHub` — it does not capture again.

## Enable

```powershell
# Pattern B: Qoresence owns the physical card
python -m qoresence.cli --play --deck --monitor --streamer-device 0 --streamer-fps 60

# Optional: limit display width
--monitor-max-width 1280
```

## HUD presets

| Preset | Shows |
|--------|-------|
| `minimal` | Frame only |
| `situation` | Frame + score/quarter/down strip |
| `full` | Situation + controller + frame age/seq (default) |

Press **`p`** in the window to cycle presets.

## Install

```powershell
pip install "qoresence[monitor]"
# or
pip install opencv-python
```

## Latency

| Glass | Lag |
|-------|-----|
| **Stem Program** (`--stem-program`) | Pattern B operator eye |
| **Retina Monitor** | Same FrameHub blit |
| OBS Preview (physical card) | Pattern A only |
| Deck JPEG | Preview only |

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Black / "waiting for FrameHub" | Streamer not running or wrong device |
| Window never opens | Install opencv-python |
| Esc or close | Stops only the monitor window |
