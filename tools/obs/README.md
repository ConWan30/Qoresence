# OBS — Retina Clutch Lens (Browser Source)

## Capture ownership (Qoresence owns the card)

**One physical HDMI/DShow card has one owner.** Recommended: **Qoresence**.

| Pattern | Physical card | Qoresence streamer | OBS |
|---------|---------------|--------------------|-----|
| **B (recommended)** | **Qoresence** `--streamer-device 0` | Physical e.g. `USB3.0 Video` | **No** Video Capture on that device; Browser Sources: **pixels** `/obs-live.html` + **Lens** `/overlay.html` |
| A (legacy) | OBS Video Capture | **OBS Virtual Camera** index | VCam → Qoresence |

Full guide: **[docs/OBS_OWNS_CARD.md](../../docs/OBS_OWNS_CARD.md)**

```text
# Close OBS physical capture first, then:
python -m qoresence.cli --streamer-list
python -m qoresence.cli --play --deck --monitor --streamer-device 0 --streamer-fps 60
```

Low-lag eye: **Retina Monitor** (`--monitor`) or Deck LIVE. Audience RTMP: OBS **Display/Game Capture**, not dual-open of the card. Audience live to X: OBS Custom Streaming Server → X Live Studio. Recipe: **[docs/X_LIVE_STUDIO.md](../../docs/X_LIVE_STUDIO.md)**. Qoresence does not ingest or restream HDMI.

---

## Correct setup (Pattern B pixels + Lens)

1. Start Qoresence on the **physical** card:
   ```text
   python -m qoresence.cli --play --deck --streamer-device 0 --streamer-fps 60
   ```
2. Confirm Deck is up:
   ```text
   curl http://127.0.0.1:8765/health
   ```
   Expect `"ok": true`. Also open `http://127.0.0.1:8765/obs-live.html` in Edge — brand must show even if the feed is dark.
3. **OBS scene LIVE** — two Browser Sources (1920×1080), Lens on top:

   | Layer | Field | Value |
   |-------|--------|--------|
   | **Pixels (bottom)** | **URL** | `http://127.0.0.1:8765/obs-live.html` (**not** raw `/video`, **not** `file:///…`) |
   | | Size | **1920 × 1080** |
   | | FPS | `60` |
   | | Shutdown / Refresh | Shutdown **OFF** · Refresh when active **ON** |
   | **Lens (top)** | **URL** | `http://127.0.0.1:8765/overlay.html` |
   | | Size | **1920 × 1080** |
   | | FPS | `30` (or 60) |
   | | Custom CSS | *(leave empty)* |
   | | Shutdown / Refresh | Shutdown **OFF** · Refresh when active **ON** |

4. **Do not** add Video Capture Device for the same physical HDMI card while Qoresence is running.

5. **X Live helper** — `tools/obs/pattern_b_x_live.ps1` clears Safe Mode cleanly, points the LIVE pixels Browser Source at `/obs-live.html`, starts `obs64 --startstreaming`, and reports `OBS_NORMAL_MODE` / `SAFE_MODE` plus `STREAM_MARK_OK` / `MISSING` from the latest log (never prints `service.json` keys).

6. **Test outside OBS first** — `obs-live.html` then `overlay.html` in Edge.

## Do **not** use

| Wrong | Why |
|-------|-----|
| `http://127.0.0.1:8765/video?fps=60` as Browser Source | CEF often stays black; use `/obs-live.html` |
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
