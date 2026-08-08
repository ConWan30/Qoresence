# Novel stack

What is distinctive about Qoresence (vs “another OBS plugin bot”).

## 1. One brain → N glasses

`RetinaEventBus` + `SituationModel` are the brain. Surfaces are thin:

- **Lens** — transparent OBS Browser Source (`/overlay.html`)
- **Rail / Ghost Theater** — local Deck (`/deck.html`)
- **LIVE** — MJPEG ops preview (`/video`)
- **Retina Monitor** — native OpenCV blit from FrameHub
- **Twitch panel** — optional extension HTML

No duplicated situation engines per glass.

## 2. Capture ownership (Pattern B recommended)

```text
PS5 → HDMI card → Qoresence StreamerRuntime (physical owner)
OBS (optional) → Browser Source Lens + game/display capture for RTMP
```

**One DShow device, one owner.** Pattern A (OBS → Virtual Cam → Qoresence) remains documented as legacy.

## 3. FrameHub — zero second capture

Streamer already owns BGR frames. It:

1. Pushes JPEG ring (`clip_buffer`) for Foundry / LIVE  
2. Publishes copy + `clock_ns` + monotonic `seq` to **FrameHub**

Monitor and IVC **only read**. Closing monitor does not stop capture.

## 4. Input–Video Coupler

HID edges → `InputRing` → IVC samples FrameHub stamp at 10–20 Hz →  
inputs in lag band `[t_video − lag_hi, t_video − lag_lo]` → `coupling ∈ [0,1]` bus event.

Default lag 20–120 ms; legacy Pattern A VCam often needs ~200 ms hi (`QORESENCE_IVC_LAG_HI_MS`).

## 5. Local Foundry

True ring-buffer MP4 from capture path + optional `*.buttons.json` with `frame_seq` on edges. Deck can play clips without Helix.

## 6. Causal bus contract

Every event: `session_id`, `clock_ns` (monotonic), `source_lobe`, typed payload.  
Cross-lobe correlation uses time windows and optional `causal_parent_ns` — not wall-clock wall-of-text logs alone.

## Stack diagram

```text
Controller ──► InputRing ──┐
                           ├──► IVC ──► coupling_score ──► Bus
Streamer ──► FrameHub ─────┘              │
     │                                    ▼
     ├── clip_buffer ──► Foundry / LIVE   Situation / ClutchBot
     └── get_current_frame ──► Visual/OCR
```

See also in-repo: `docs/ARCHITECTURE.md`, `docs/CONTROLLER_VIDEO_SYNC.md`, `docs/RETINA_MONITOR.md`.
