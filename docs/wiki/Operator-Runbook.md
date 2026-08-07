# Operator runbook (Windows pilot)

## Daily Pattern A

1. **OBS**  
   - Video Capture Device = physical HDMI card  
   - **Tools → Start Virtual Camera**

2. **List devices**
   ```text
   python -m qoresence.cli --streamer-list
   ```
   Note the **OBS Virtual Camera** index.

3. **Play stack**
   ```text
   python -m qoresence.cli --play --deck --streamer-device <VCAM> --streamer-fps 30
   ```

4. **Optional glass + pad**
   ```text
   $env:QORESENCE_IVC_LAG_HI_MS = "200"
   python -m qoresence.cli --play --deck --monitor --controller --streamer-device <VCAM> --streamer-fps 30
   ```

5. **OBS Browser Source** (Lens)  
   URL: `http://127.0.0.1:8765/overlay.html`  
   (HTTP — not `file://`)

6. **Theater**  
   `http://127.0.0.1:8765/deck.html`

## Health checks

| Signal | Good |
|--------|------|
| Log `Capture opened` | 1280×720 (or your size) @ target FPS |
| Log `OBS Virtual Camera` | Pattern A |
| Log `Controller HID opened` | DualSense Edge listed |
| Log `IVC started` | only with `--controller` |
| Log `Retina Monitor on` | only with `--monitor` |
| `/api/situation` → `video.has_frame` | true |
| `/api/situation` → `controller` | present when IVC running |

## Never

- `--streamer-device` on the **physical** card while OBS holds it  
- Using Deck LIVE as your aim monitor for competitive play  
- Expecting coupling without PC-visible DualSense (USB / Remote Play)

## Clip + buttons

```text
POST http://127.0.0.1:8765/api/clip  {"seconds":5}
```

Produces `clips/hdmi_clip_*.mp4` and, if inputs in window, `*.buttons.json`.
