# WebRTC LIVE (novel wiring)

**Same rule as Retina Monitor / IVC:** Qoresence streamer owns the physical card.  
WebRTC **subscribes** to **FrameHub** BGR frames — it never opens a second DShow device.

```text
PS5 → USB3.0 Video → StreamerRuntime (grabber thread)
                         ├─ FrameHub ──► WebRTC track ──► deck.html <video>
                         ├─ clip_buffer JPEG ──► /video MJPEG (fallback)
                         └─ OCR / A2A / Monitor
```

---

## Install

```powershell
pip install aiortc av
# or
pip install -e ".[webrtc]"
```

---

## API

| Endpoint | Role |
|----------|------|
| `GET /api/webrtc/status` | `{ available, peers, source: "frame_hub" }` |
| `POST /api/webrtc/offer` | Body `{ sdp, type, fps?, max_width? }` → answer |
| `GET /video?fps=60` | MJPEG fallback |

Deck Theater auto-tries WebRTC on LIVE, then falls back to MJPEG.

---

## Why this is “novel” for Qoresence

| Glass | Source |
|-------|--------|
| Retina Monitor | FrameHub blit |
| IVC | FrameHub stamp |
| **WebRTC LIVE** | FrameHub → RTC track |
| MJPEG LIVE | clip_buffer JPEG ring |

One brain, **N glasses** — WebRTC is another glass, not a second capture pipeline.

---

## Limits (v1)

- Localhost only (`127.0.0.1`) — no STUN/TURN yet  
- Video only (no game audio)  
- Default encode ~60 fps / max width 1280 for low-lag LIVE (capture also 60)  
- Requires `aiortc` + `av`  

---

## Verify

```powershell
# with --play --deck running and webrtc installed:
(Invoke-RestMethod http://127.0.0.1:8765/api/webrtc/status).available
# True
Start-Process http://127.0.0.1:8765/deck.html
# stage meta should say "LIVE · WebRTC (FrameHub · no second capture)"
```
