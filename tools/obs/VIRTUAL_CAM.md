# OBS Virtual Camera → Qoresence (legacy Pattern A)

**Recommended going forward:** Qoresence owns the physical card — see [docs/OBS_OWNS_CARD.md](../../docs/OBS_OWNS_CARD.md) and [README](../../README.md).

Use this runbook **only** when you need OBS Preview as the exclusive low-lag eye on the physical card.

## Rule (Pattern A)
One physical card → **OBS only**. Qoresence uses **OBS Virtual Camera**.

## Steps
1. OBS: Video Capture = physical HDMI (e.g. USB3.0 Video). Preview = game.
2. OBS: **Start Virtual Camera**.
3. List devices:
   ```text
   python -m qoresence.cli --streamer-list
   ```
4. Note index of **OBS Virtual Camera** (look for `[legacy — only if OBS owns physical card]`).
5. Start Qoresence (replace `N`):
   ```text
   python -m qoresence.cli --play --deck --streamer-device N --streamer-fps 30
   ```
6. Lens: Browser Source `http://127.0.0.1:8765/overlay.html` (not `file://`).
7. Deck: `http://127.0.0.1:8765/deck.html` (ops / clips — not competitive eye).
8. Optional: `$env:QORESENCE_IVC_LAG_HI_MS = "200"` for VCam lag.

## Verify
```powershell
(Invoke-RestMethod http://127.0.0.1:8765/health).state.video.has_frame
# expect True within ~10s
```

## If open fails
- Device busy on physical index → use VCam index, not `0` (Pattern A only).  
- VCam black → Start Virtual Camera in OBS.  
- Privacy guard → wrong device (webcam).  

## Do not
- Open USB3.0 in both OBS and Qoresence.  
- Use Theater LIVE as your aim monitor (use OBS Preview under Pattern A; Retina Monitor under Pattern B).  
