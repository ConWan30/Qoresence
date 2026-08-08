# Retina Deck and Monitor

## Deck (browser)

| Path | Role |
|------|------|
| `/deck.html` | Ghost Theater / Rail — moments, LIVE, clips |
| `/overlay.html` | Clutch Lens for OBS Browser Source |
| `/video` | MJPEG LIVE from clip_buffer (ops glass) |
| `/api/situation` | Snapshot JSON |
| `/api/clip` | Export Foundry MP4 |

Start: `--play --deck` or `--deck` with lobes enabled.

## Retina Monitor (native)

- Flag: `--monitor` (default OFF)  
- Blits FrameHub frames via OpenCV HighGUI  
- Optional situation strip + pad/coupling HUD  
- Closing window **does not** stop streamer/Deck  

```text
pip install "qoresence[monitor]"
python -m qoresence.cli --play --deck --monitor --streamer-device 0 --streamer-fps 60
```

Docs: [RETINA_MONITOR.md](https://github.com/ConWan30/Qoresence/blob/main/docs/RETINA_MONITOR.md)
