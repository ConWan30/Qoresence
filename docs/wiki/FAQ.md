# FAQ

### Black frames / failed open device 0
Something else already owns the physical card (usually OBS Video Capture). Close/disable that source, then restart Qoresence with `--streamer-device 0`. Only use OBS Virtual Camera if you intentionally run legacy Pattern A.

### Controller failed to start
Pad must be PC-visible. Plug USB or use Remote Play. Log lists HID candidates. Video path continues without pad.

### Coupling always ~0
No edges in lag band, or controller off. Press buttons; widen `QORESENCE_IVC_LAG_HI_MS` only if using Virtual Cam lag.

### Coupling always ~1 / noisy buttons
DualSense Edge report layout may still chatter; pipeline is valid — decode harden is on roadmap.

### Deck LIVE lags behind TV
Expected for MJPEG ops glass. Theater prefers WebRTC from FrameHub. Use Retina Monitor for the local blit; LIVE / Mobile Glass for “is the path alive?”

### Phone cannot open Mobile Glass
`127.0.0.1` on the phone is the phone itself. Restart with `--deck-bind 0.0.0.0` and scan the Theater QR. The PC cannot find phones on Wi‑Fi or open Safari/Chrome remotely.

### Android Glass is black / never says LIVE · CINEMA
WebView cannot play MJPEG. Rebuild the cinema APK (`native/build-apk.ps1`). `/live.jpg` is 503 until HDMI has a frame — wait for `--play` to push into ClipBuffer. Home / Pop-out keeps pumping in PiP.

### Title flipped to the wrong game
Pass `--game-profile madden_27` (or `ncaa_football_27`). An explicit pin is not yanked when optics lock a stranger pair. Pause/menu is `overlay-rejected` (no title claim).

### No buttons.json after clip
No InputRing events in export window (controller off or silent pad).

### clients: 0 on overlay
Use `http://127.0.0.1:8765/overlay.html` not `file://`; ensure Deck process is running.
