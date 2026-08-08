# OBS — Retina Clutch Lens (Browser Source)

## Capture ownership (Qoresence owns the card)

**One physical HDMI/DShow card has one owner.** Recommended: **Qoresence**.

| Pattern | Physical card | Qoresence streamer | OBS |
|---------|---------------|--------------------|-----|
| **B (recommended)** | **Qoresence** `--streamer-device 0` | Physical e.g. `USB3.0 Video` | **No** Video Capture on that device; **Browser Source** for Lens only |
| A (legacy) | OBS Video Capture | **OBS Virtual Camera** index | VCam → Qoresence |

Full guide: **[docs/OBS_OWNS_CARD.md](../../docs/OBS_OWNS_CARD.md)**

```text
# Close OBS physical capture first, then:
python -m qoresence.cli --streamer-list
python -m qoresence.cli --play --deck --monitor --streamer-device 0 --streamer-fps 60
```

Low-lag eye: **Retina Monitor** (`--monitor`) or Deck LIVE. Audience RTMP: OBS **Display/Game Capture**, not dual-open of the card.

---

## Correct setup (Lens only)

1. Start Qoresence on the **physical** card:
   ```text
   python -m qoresence.cli --play --deck --streamer-device 0 --streamer-fps 60
   ```
2. Confirm Deck is up:
   ```text
   curl http://127.0.0.1:8765/health
   ```
   Expect `"ok": true`.
3. **OBS → Sources → + → Browser**
   | Field | Value |
   |-------|--------|
   | **URL** | `http://127.0.0.1:8765/overlay.html` (**not** `file:///…`) |
   | **Size** | **1920 × 1080** |
   | FPS | `30` (or 60) |
   | Custom CSS | *(leave empty)* |
   | **Shutdown source when not visible** | **OFF** |
   | **Refresh browser when scene becomes active** | **ON** |

4. **Do not** add Video Capture Device for the same physical HDMI card while Qoresence is running.

5. **Test outside OBS first** — open `http://127.0.0.1:8765/overlay.html` in Edge.

## Do **not** use

| Wrong | Why |
|-------|-----|
| `file:///C:/Users/.../overlay.html` | No same-origin Deck; WS fails |
| Physical card in OBS **and** Qoresence | Dual-open thrash |
| `tools/obs/presence_overlay.html` via `file://` | Prefer Deck Lens URL |

## Verify OBS Lens is connected

```powershell
(Invoke-RestMethod http://127.0.0.1:8765/health).clients
```

- **`clients >= 1`** → Browser Source reached Deck WS  
- **`clients: 0`** → wrong URL, Deck down, or refresh Browser Source  

## Legacy Pattern A (OBS owns card)

If you must keep OBS Preview on the physical card: Start Virtual Camera, pass VCam index to Qoresence. See [VIRTUAL_CAM.md](VIRTUAL_CAM.md).
