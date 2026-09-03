# Capture card ownership — Qoresence first

**One physical DirectShow device has one owner.** Going forward the **recommended** pilot is **Qoresence owns the card**.

---

## 1. Role split (recommended)

| Job | Owner | Notes |
|-----|--------|--------|
| **Physical HDMI capture** | **Qoresence** StreamerRuntime | `--streamer-device` = physical card (e.g. `USB3.0 Video` index **0**) |
| **Low-lag operator eye** | **Stem Program** / Retina Monitor (`--stem-program` / `--monitor`) | FrameHub blit; replaces OBS Preview. HUD burn-in is Monitor-only |
| **On-stream HUD** | **Lens** Browser Source in OBS | `http://127.0.0.1:8765/overlay.html` — **Browser only**, no Video Capture on the same card |
| **Audience stream** | OBS (optional) | Window/Display/Game capture of the gameplay monitor, **or** NDI/other — **not** the same DShow device Qoresence holds |
| **Situation, clips, ClutchBot** | Qoresence | True HDMI ring + OCR + agents |

---

## 2. One-card ownership rule

**Never open the same physical DirectShow device in OBS and Qoresence at the same time.**

| Wrong | Result |
|-------|--------|
| OBS Video Capture = USB3.0 Video **and** `--streamer-device 0` | Device busy, black frames, thrash |
| Habit of leaving OBS on the card while “testing” Qoresence | Silent failures |

| Right | Result |
|-------|--------|
| **Qoresence holds physical card** | Full-rate frames for OCR, Foundry, Monitor, IVC |
| OBS uses Browser Source for Lens only | Overlay without fighting DShow |
| (Legacy) OBS holds card → Virtual Cam → Qoresence | Pattern A — still supported, higher lag |

---

## 3. Pattern B (recommended) — Qoresence owns card

```text
PS5 HDMI
  → capture card (physical DShow, e.g. USB3.0 Video)
  → Qoresence StreamerRuntime (--streamer-device 0)
  → FrameHub / clip_buffer / OCR / Deck / ClutchBot / Monitor
```

**OBS setup when streaming:**

1. **Remove or disable** any **Video Capture Device** source that points at the same physical card.  
2. **Do not** Start Virtual Camera *from that card* if Qoresence already owns it.  
3. Add **Browser Source** → `http://127.0.0.1:8765/overlay.html` for the Lens HUD.  
4. Capture the stream with **Game Capture / Display Capture / Window Capture** of the PS5/TV path as you prefer — not dual-open of the card. Audience live to **X**: OBS Custom Streaming Server → X Live Studio ([X_LIVE_STUDIO.md](X_LIVE_STUDIO.md)).

---

## 4. Pattern A (legacy) — OBS owns card

```text
PS5 → card → OBS Video Capture → Virtual Camera → Qoresence --streamer-device <OBS_VCAM>
```

Use only if you need OBS Preview as the exclusive low-lag eye and accept Virtual Cam lag for Qoresence.  
Widen IVC: `$env:QORESENCE_IVC_LAG_HI_MS = "200"`.

---

## 5. Step-by-step — Pattern B (daily)

1. **Close OBS capture of the physical card**  
   - Delete/disable that Video Capture Device source, or exit OBS if unsure.

2. **List devices**  
   ```text
   python -m qoresence.cli --streamer-list
   ```  
   Use the **physical** row (e.g. `USB3.0 Video`), not `OBS Virtual Camera`, not webcam.

3. **Start Qoresence** (example — index **0** on this machine):  
   ```text
   python -m qoresence.cli --play --deck --monitor --controller --streamer-device 0 --streamer-fps 60
   ```  
   (`--play` may raise FPS to 60 if you don’t pass `--streamer-fps`; explicit is fine.)

4. **Optional stream**  
   - OBS: Browser Source Lens URL only + display/game capture for RTMP.

5. **Deck**  
   - http://127.0.0.1:8765/deck.html  

---

## 6. Verify

| Check | Expect |
|--------|--------|
| Log `streamer source` | Physical name (e.g. USB3.0 Video), not OBS Virtual Camera |
| `/health` → `video.has_frame` | `true` within ~10s |
| Eye-check PNG | Game field, not black/webcam |
| Dual-open | None — OBS not holding the same index |

---

## Scoreboard OCR (gaming)

Default engine is **PaddleOCR** (better on stylized CFB HUD digits than EasyOCR). Fallback: EasyOCR.

```powershell
$env:QORESENCE_SCOREBOARD_OCR = "paddle"   # or auto | easyocr | tesseract
pip install "paddlepaddle>=2.6" "paddleocr>=2.7"
```

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|----------------|-----|
| `Failed to open capture source 0` | OBS still owns card | Disable OBS Video Capture / close OBS |
| Black / frozen | Wrong index or HDCP | `--streamer-list`; eye-check PNG |
| Webcam privacy guard | Wrong device | Don’t use camera index |
| Want OBS Preview lag feel | Pattern A | VCam index + stop Qoresence on physical |

---

## 8. Related

- [RETINA_MONITOR.md](RETINA_MONITOR.md) — native glass on FrameHub  
- [CONTROLLER_VIDEO_SYNC.md](CONTROLLER_VIDEO_SYNC.md) — IVC lag (physical can use default 120 ms)  
- [tools/obs/README.md](../tools/obs/README.md) — Lens Browser Source only under Pattern B
- [X_LIVE_STUDIO.md](X_LIVE_STUDIO.md) — audience live to X via OBS Custom RTMP (not a Qoresence encoder)
