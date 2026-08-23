# Retina Deck and Monitor

## Deck (browser)

| Path | Role |
|------|------|
| `/deck.html` | Ghost Theater / Rail — moments, LIVE, clips, Mobile Glass QR |
| `/overlay.html` | Clutch Lens for OBS Browser Source |
| `/mobile.html` | Mobile Glass — same FrameHub on a phone (WebRTC / MJPEG) |
| `/video` | MJPEG LIVE from clip_buffer (ops glass) |
| `/api/situation` | Snapshot JSON |
| `/api/glass-link` | Honest glass URL + whether LAN bind is on |
| `/api/clip` | Export Foundry MP4 |

Start: `--play --deck` or `--deck` with lobes enabled.

**Phone:** localhost `/mobile.html` is for the PC. Same Wi‑Fi needs `--deck-bind 0.0.0.0`, then scan the Theater QR. The PC cannot open the phone browser. See [Mobile-Glass](Mobile-Glass).

## Retina Monitor (native)

- Flag: `--monitor` (default OFF) or `--stem-program` (Program-out, implies monitor)  
- Blits FrameHub frames via OpenCV HighGUI  
- Optional situation strip + pad/coupling HUD (Monitor blit only — FrameHub stays clean)  
- Closing window **does not** stop streamer/Deck  
- See [Retina-Stem](Retina-Stem) for the situation-directed program bus

```text
pip install "qoresence[monitor]"
python -m qoresence.cli --play --deck --stem-program --streamer-device 0 --streamer-fps 60
```

Docs: [RETINA_MONITOR.md](https://github.com/ConWan30/Qoresence/blob/main/docs/RETINA_MONITOR.md)
