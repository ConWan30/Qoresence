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
Pass `--game-profile madden_27` (or `ncaa_football_27`). The profile is **persisted** to `~/.qoresence/last_game_profile` — next session reuses it automatically without re-passing the flag. You can also set `QORESENCE_GAME_PROFILE` env. An explicit pin (CLI / env / last session) is not yanked when optics lock a stranger pair. First-run with no pin falls back to `ncaa_football_27` but is not pinned, so optics can still lock the live title. Pause/menu is `overlay-rejected` (no title claim).

### A2A chat is too quiet / too spammy
Default chat cooldown is **25s** (was 45s). Tune via `QORESENCE_A2A_CHAT_COOLDOWN_S`. Near-duplicate window is 120s with a 40-char prefix match (was 24-char, which over-vetoed natural variations). Soft-path digit check now only flags explicit scorelines (`X-Y`); bare numbers like "gained 12 yards" are no longer vetoed.

### Outcome lobe says "temporal_desync"
The outcome lobe emits a `HEARTBEAT` on every visual context it processes, so fusion sees it's alive even when the game state is stable (no score changes for >5s). If you still see `temporal_desync`, check that the visual lobe is actually publishing `VISUAL_CONTEXT` events — the outcome lobe is silent without them.

### No buttons.json after clip
No InputRing events in export window (controller off or silent pad).

### clients: 0 on overlay
Use `http://127.0.0.1:8765/overlay.html` not `file://`; ensure Deck process is running.
