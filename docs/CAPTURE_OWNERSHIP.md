# Capture ownership — Pattern A vs B

**Hard rule:** one physical DirectShow HDMI/capture device has **one owner**.  
Never open the same USB card in OBS **and** Qoresence at the same time (black frames, thrash, failed open).

List devices:

```text
python -m qoresence.cli --streamer-list
```

Prefer the physical row (e.g. `USB3.0 Video` — recommended). Default `--streamer-device -1` auto-picks by name.

---

## Pattern A — OBS owns card

**When:** OBS Preview is your low-lag competitive eye and you accept Virtual Cam lag for Qoresence.

```text
PS5 → HDMI card → OBS Video Capture (physical)
                 → OBS Start Virtual Camera
                 → Qoresence --streamer-device <OBS_VCAM_INDEX>
```

| Job | Owner |
|-----|--------|
| Physical card | **OBS** |
| Qoresence streamer | **OBS Virtual Camera** index only |
| Lag | Higher for FrameHub / OCR / IVC |

```powershell
# OBS: Video Capture = USB3.0 Video → Tools → Start Virtual Camera
python -m qoresence.cli --streamer-list
# note OBS Virtual Camera index (e.g. 2)
$env:QORESENCE_IVC_LAG_HI_MS = "200"   # optional wider IVC band
python -m qoresence.cli --play --deck --streamer-device 2 --streamer-fps 30
```

Lens: Browser Source `http://127.0.0.1:8765/overlay.html`

See also: [tools/obs/VIRTUAL_CAM.md](../tools/obs/VIRTUAL_CAM.md)

---

## Pattern B — Qoresence owns card (recommended pilot)

**When:** Low-lag pilot, native Retina Monitor, scoreboard VLM, full-rate FrameHub.

```text
PS5 → HDMI card (physical DShow)
    → Qoresence StreamerRuntime (owns card)
    → FrameHub / Monitor / OCR / Deck LIVE / ClutchBot

OBS (optional stream): Browser Source for Lens only
  + Game/Display/Window capture for RTMP
  — do NOT open the same physical card
```

| Job | Owner |
|-----|--------|
| Physical card | **Qoresence** |
| OBS | Lens Browser Source + non-DShow stream capture |
| Lag | Lowest for Qoresence glass / OCR |

```powershell
# OBS: remove/disable Video Capture on USB3.0 Video
python -m qoresence.cli --streamer-list
python -m qoresence.cli --play --deck --monitor --streamer-fps 60 --a2a
# --streamer-device -1 (default) auto-picks USB3.0 Video by name
```

Deck: http://127.0.0.1:8765/deck.html  
Lens: http://127.0.0.1:8765/overlay.html

---

## Goal → pattern

| Goal | Pattern |
|------|---------|
| Low-lag pilot / native monitor / scoreboard VLM | **B** |
| OBS as broadcast director (Preview on card) | **A** |

---

## Conflict symptoms

| Symptom | Likely cause |
|---------|----------------|
| Failed open / black frames | Dual-open or card unplugged |
| Privacy guard on webcam | Wrong index — use `--streamer-list` |
| Device busy on physical index | OBS still holds card → Pattern A VCam, or free the source |

Extended operator detail: [OBS_OWNS_CARD.md](OBS_OWNS_CARD.md)
