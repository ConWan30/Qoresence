# FAQ

### Black frames / failed open device 0
OBS already owns the physical card. Use Virtual Cam index from `--streamer-list`.

### Controller failed to start
Pad must be PC-visible. Plug USB or use Remote Play. Log lists HID candidates. Video path continues without pad.

### Coupling always ~0
No edges in lag band, or controller off. Press buttons; widen `QORESENCE_IVC_LAG_HI_MS` for VCam.

### Coupling always ~1 / noisy buttons
DualSense Edge report layout may still chatter; pipeline is valid — decode harden is on roadmap.

### Deck LIVE lags behind TV
Expected for MJPEG ops glass. Use OBS Preview for aim; Monitor for local blit; LIVE for “is path alive?”.

### No buttons.json after clip
No InputRing events in export window (controller off or silent pad).

### clients: 0 on overlay
Use `http://127.0.0.1:8765/overlay.html` not `file://`; ensure Deck process is running.
