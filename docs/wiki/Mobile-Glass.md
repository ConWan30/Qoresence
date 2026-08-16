# Mobile Glass

Phone-friendly view of the **same** LIVE session. Source is FrameHub only. The phone is a **view**, never a capture owner.

| Path | Role |
|------|------|
| `/mobile.html` | Glass page (WebRTC primary, MJPEG fallback) |
| `/api/glass-link` | Honest URL + whether LAN bind is on |
| `/api/glass-qr` | SVG QR (only when LAN bind is on) |

## Localhost

```text
python -m qoresence.cli --play --deck --streamer-device 0
# then http://127.0.0.1:8765/mobile.html
```

## Same Wi‑Fi (opt-in)

`--play` does **not** bind `0.0.0.0`.

```text
python -m qoresence.cli --play --deck --deck-bind 0.0.0.0 --streamer-device 0
```

On Theater, scan the QR or copy the glass link. The PC cannot search for phones or open the phone browser.

## Limits

Video-only v1, muted autoplay + `playsinline` for iOS, no STUN/TURN, no public CDN.

Full doc: [docs/MOBILE_GLASS.md](https://github.com/ConWan30/Qoresence/blob/main/docs/MOBILE_GLASS.md)
