# Mobile Glass — phone view of the same LIVE aperture

Phone is a **view**, never a capture owner. Same FrameHub as Theater / Monitor / IVC.

```text
PS5 → USB3.0 Video → StreamerRuntime
                         └─ FrameHub ──► WebRTC ──► /mobile.html  <video>
                                    └──► /video MJPEG fallback
```

## Prerequisites

1. PC: `python -m qoresence.cli --play --deck` so FrameHub has frames.
2. WebRTC: `pip install aiortc av` or `pip install -e ".[webrtc]"`. Without it, the page still loads and uses MJPEG.
3. Phone on the **same Wi‑Fi** only if you opt in to LAN bind. Default is localhost.

## LAN bind (opt-in, default OFF)

Default listen is `127.0.0.1`. This is **not** a CDN and is **not** enabled by `--play`.

```powershell
python -m qoresence.cli --play --deck --deck-bind 0.0.0.0
# or
$env:QORESENCE_DECK_BIND="0.0.0.0"
```

Then on Theater use **Copy glass link**, or open `http://<pc-lan-ip>:8765/mobile.html` on the phone.

## Verify

1. `GET http://127.0.0.1:8765/api/webrtc/status` — `available` true/false is honest; `source` is `frame_hub`.
2. PC browser: `http://127.0.0.1:8765/mobile.html` — WebRTC or MJPEG fallback.
3. If LAN bind is on: phone on same Wi‑Fi opens the copied URL.
4. Confirm no second capture device is opened.

## Limits (v1)

- Video only (muted autoplay + `playsinline` for iOS). Tap-to-unmute later if audio exists.
- No STUN/TURN — cellular / remote internet viewing is out of scope.
- Multiple phones = multiple encodes from FrameHub (CPU).
- Observation strip shows score only when locked; otherwise `—`. No invented digits.

See also `docs/WEBRTC_LIVE.md`.
