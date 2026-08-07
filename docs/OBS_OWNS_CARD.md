# OBS owns the capture card — Qoresence via Virtual Camera

Pilot streamer model for Qoresence. **One physical DShow device has one owner.**

---

## 1. Role split

| Job | Owner | Notes |
|-----|--------|--------|
| **Low-lag eye on gameplay** | **OBS Preview / Program** | Physical HDMI Video Capture Device |
| **Situation, clips, ClutchBot** | **Qoresence** | Streamer source = **OBS Virtual Camera** |
| **On-stream HUD** | **Lens** Browser Source | `http://127.0.0.1:8765/overlay.html` (never `file://`) |
| **Ghost Theater LIVE `/video`** | Deck ops glass | Health / context only — **not** the competitive view |
| **Audience stream** | Twitch / RTMP from OBS | Never use Twitch delay as your personal monitor |

---

## 2. One-card ownership rule

**Never open the same physical DirectShow device in OBS and Qoresence at the same time.**

| Wrong | Result |
|-------|--------|
| OBS Video Capture = USB3.0 Video **and** `--streamer-device 0` | Device busy, black frames, thrash, failed start |
| Two apps “sharing” the card | Unreliable DShow exclusive access |

| Right | Result |
|-------|--------|
| OBS holds physical card → Virtual Cam → Qoresence | Stable pilot path |
| Lab only: Qoresence holds physical; OBS does **not** open that device | Pattern B |

---

## 3. Pattern A (recommended) — OBS owns card

```text
PS5 HDMI
  → capture card (physical DShow, e.g. USB3.0 Video)
  → OBS Video Capture Device
  → OBS Start Virtual Camera
  → Qoresence StreamerRuntime (--streamer-device <OBS Virtual Camera index>)
  → clip_buffer / Deck / ClutchBot / Lens
```

OBS Preview = real-time eye.  
Qoresence = scores, moments, local HDMI-style clips from the **Virtual Cam** frames, overlays.

---

## 4. Pattern B (lab only) — Qoresence owns card

```text
PS5 HDMI → card → Qoresence --streamer-device 0 (physical)
OBS must NOT open that physical device (no dual-open).
```

Use only when you are not running OBS capture on the same card.  
For daily streaming, prefer **Pattern A**.

---

## 5. Step-by-step — Pattern A

1. **OBS**  
   - Sources → **Video Capture Device** = physical HDMI card (e.g. `USB3.0 Video`).  
   - Confirm Preview shows game (not webcam / black HDCP).

2. **OBS → Tools → Start Virtual Camera**  
   - Leave Virtual Camera running while Qoresence is live.

3. **Lens (on-stream HUD)**  
   - Browser Source URL: `http://127.0.0.1:8765/overlay.html`  
   - 1920×1080, transparent, above game if stacking.  
   - See [tools/obs/README.md](../tools/obs/README.md).

4. **List devices**  
   ```text
   python -m qoresence.cli --streamer-list
   ```  
   Find the row whose name is **OBS Virtual Camera** (annotated when present).

5. **Start Qoresence** (example index `2` — use **your** list):  
   ```text
   python -m qoresence.cli --play --deck --streamer-device 2 --streamer-fps 30
   ```  
   Do **not** point `--streamer-device` at the physical card index while OBS holds it.

6. **Deck** (ops, not competitive view):  
   - http://127.0.0.1:8765/deck.html  

---

## 6. Verify checklist

| Check | Expect |
|--------|--------|
| `(Invoke-RestMethod http://127.0.0.1:8765/health).state.video.has_frame` | `true` within ~10s |
| `...health).clients` | ≥ 1 when Lens/Deck open |
| Foundry **Make HDMI Clip** | MP4 under `clips/` + REPLAY works |
| Lens pill | Updates when scorebug is readable |
| OBS Preview | Still smooth (physical card) |

Theater LIVE is **ops glass** (is HDMI path alive?). Do not use it as your aim/monitor.

---

## 7. Failure matrix

| Symptom | Likely cause | Fix |
|---------|----------------|-----|
| `Failed to open capture source 0` | OBS already owns physical card | Start Virtual Cam; use VCam index |
| Black / frozen VCam | Virtual Camera not started | OBS → Start Virtual Camera |
| Wrong device | Habit of `--streamer-device 0` | Re-run `--streamer-list` |
| `PRIVACY GUARD` / person in frame | Webcam index or wrong source | Use VCam or allowed capture name only |
| `has_frame: false` | Streamer not running / wrong index | Check list + VCam + logs |
| Lens empty / `clients: 0` | `file://` or WS 403 / Deck down | HTTP overlay URL; restart `--play --deck` |

---

## 8. Phase 2 — Native Retina Monitor

A **native Retina Monitor** blits the **same** frames Qoresence already holds (`FrameHub` ← streamer) with no JPEG browser path and **no second capture open**.

```text
python -m qoresence.cli --play --deck --monitor --streamer-device <OBS_VCAM> --streamer-fps 30
```

- Still one physical-card owner (usually OBS + VCam).  
- Closing the monitor does not stop Deck/streamer.  
- Full docs: **[RETINA_MONITOR.md](RETINA_MONITOR.md)**

---

## 9. Controller sync (optional)

DualSense HID → **InputRing** + **Input–Video Coupler** joins button edges to FrameHub `clock_ns` / `frame_seq`. **Default OFF** (`--controller`). Independent of who owns the HDMI card; VCam may need a wider lag band (`QORESENCE_IVC_LAG_HI_MS`).

Full docs: **[CONTROLLER_VIDEO_SYNC.md](CONTROLLER_VIDEO_SYNC.md)**

---

## Related

- Operator runbook: [tools/obs/VIRTUAL_CAM.md](../tools/obs/VIRTUAL_CAM.md)  
- Lens Browser Source: [tools/obs/README.md](../tools/obs/README.md)  
