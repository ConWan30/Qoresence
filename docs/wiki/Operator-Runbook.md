# Operator runbook (Windows pilot)

## Daily Pattern B (recommended) — Qoresence owns card

1. **OBS** (if streaming)  
   - **Remove/disable** any Video Capture Device on the physical HDMI card  
   - Browser Source for Lens only: `http://127.0.0.1:8765/overlay.html`  
   - Stream via Game/Display/Window Capture of the gameplay path — not dual-open DShow

2. **List devices**
   ```text
   python -m qoresence.cli --streamer-list
   ```
   Pick the **physical** row (e.g. `USB3.0 Video` — marked recommended), not OBS Virtual Camera, not webcam.

3. **Play stack**
   ```text
   python -m qoresence.cli --play --deck --monitor --controller --streamer-device 0 --streamer-fps 60
   ```

4. **Theater**  
   `http://127.0.0.1:8765/deck.html`

## Health checks

| Signal | Good |
|--------|------|
| Log `Capture opened` / streamer source | Physical name (e.g. USB3.0 Video), not OBS Virtual Camera |
| Log `Controller HID opened` | DualSense Edge listed (if `--controller`) |
| Log `IVC started` | only with `--controller` |
| Log `Retina Monitor on` | only with `--monitor` |
| `/api/situation` → `video.has_frame` | true |
| `/api/situation` → `controller` | present when IVC running |

## Never

- Open the **physical** card in OBS **and** Qoresence at the same time  
- Using Deck LIVE as your aim monitor for competitive play  
- Expecting coupling without PC-visible DualSense (USB / Remote Play)

## Legacy Pattern A

If you must keep OBS Preview on the physical card: Start Virtual Camera, pass VCam index to Qoresence, widen `QORESENCE_IVC_LAG_HI_MS=200`. See [tools/obs/VIRTUAL_CAM.md](../../tools/obs/VIRTUAL_CAM.md).

## Clip + buttons

```text
POST http://127.0.0.1:8765/api/clip  {"seconds":5}
```

Produces `clips/hdmi_clip_*.mp4` and, if inputs in window, `*.buttons.json`.
