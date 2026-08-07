# OBS — Retina Clutch Lens (Browser Source)

## Correct setup

1. Start Deck / play stack:
   ```text
   python -m qoresence.cli --play --deck
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

4. **Layer order** — place Browser Source **above** Video Capture Device (HDMI PS5).  
   Lens `html,body{background:transparent}` is already set in `qoresence/deck/overlay.html`.

5. **Test outside OBS first** — open `http://127.0.0.1:8765/overlay.html` in Edge.  
   Expect eye top-right (`● live …`) when Deck has a situation; pill only when scorebug fields exist.  
   If Edge works but OBS does not → layer order / OBS cache: right-click Browser Source → **Refresh**.

## Do **not** use

| Wrong | Why |
|-------|-----|
| `file:///C:/Users/.../overlay.html` | No same-origin Deck; WS fails → FIN_WAIT_2, `clients:0` |
| `http://127.0.0.1:8765/retina` | WebSocket path only (HTTP 404) |
| `ws://127.0.0.1:8765/retina` as Browser URL | Not a page |
| `http://127.0.0.1:8765/overlay` | Missing `.html` → 404 |
| `tools/obs/presence_overlay.html` via `file://` | Legacy bus overlay; use Deck Lens URL above |

## Verify OBS is connected

```powershell
(Invoke-RestMethod http://127.0.0.1:8765/health).clients
```

- **`clients >= 1`** → Browser Source reached `ws://…/retina`
- **`clients: 0`** + FIN_WAIT_2 → wrong URL, Deck down, or CEF still on a dead tab — fix URL, **Refresh** on the source

## Live stack notes (why pill is empty)

1. **OBS URL / layer** — this README.  
2. **Scorebug OCR** — LocalVLM runs EasyOCR on football for ONNX *and* heuristic (`QORESENCE_DISABLE_SCOREBOARD_OCR=1` only in tests).  
3. **Frame source** — `--play` uses **streamer** (DShow HDMI/UVC idx 0), not mss desktop.  
   ```text
   python -m qoresence.cli --streamer-list
   python -m qoresence.cli --play --deck --streamer-device 0
   ```
   Desktop (`--screen`) is optional and wrong for PS5 HDMI scoreboard OCR.

## Legacy presence overlay

`presence_overlay.html` talks to the **event-bus** WebSocket (`ws://127.0.0.1:8765` root), not Retina Deck `/retina`. Prefer **Clutch Lens** (`/overlay.html`) for `--play --deck`.
