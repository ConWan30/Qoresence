# Spout Glass — FrameHub PGM into OBS (no dual-open)

**Status: spike.** Default **OFF**. Not implied by `--play`. DualSense stays on the PS5.

## Problem

Pattern B X Live today often uses `obs-live.html` (MJPEG) inside OBS CEF Browser Source → lag / CEF tax. Dual-opening the physical card with OBS Video Capture is **forbidden**.

## Goal

**Spout Glass** subscribes to **FrameHub** (same process as Streamer) and publishes a **Spout2** sender (default name `QoresencePGM`). OBS uses **Spout Capture** for pixels. **Clutch Lens** stays a Browser Source on `http://127.0.0.1:8765/overlay.html` only.

| Layer | Owner | Notes |
|-------|--------|------|
| Capture card | Qoresence | Pattern B — never dual-open |
| PGM pixels | Spout Glass → OBS Spout Capture | `--spout-glass` |
| HUD digits | OBS Browser Source `overlay.html` | ConfirmTicket + `score_vlm_locked` + fresh ticket only |
| Audience RTMP | OBS → X Live Studio | Not Qoresence ([X_LIVE_STUDIO.md](X_LIVE_STUDIO.md)) |

Product face / API mouth: [X_GLASS.md](X_GLASS.md). Spout is a **local pixel pipe**, not X API.

## Laws

1. Qoresence owns the card; OBS never adds Video Capture on the same DShow device.
2. Subscribe only — **no** DShow open in this module.
3. `--spout-glass` default **OFF**; **not** implied by `--play`.
4. Never hold the streamer / grab lock; latest-frame copy; **drop under load**.
5. Align `frame_seq` / `clock_ns` from FrameHub where possible (`/health` → `spout`).
6. Overlay digits unchanged: ConfirmTicket + `score_vlm_locked` + ticket-fresh.
7. No RTMP / WHIP / Twitch / `--x-glass` in this spike.

## Operator recipe (Windows)

1. Pattern B: start Qoresence with Spout Glass:

```powershell
python -m qoresence.cli --play --deck --spout-glass --streamer-fps 60
# optional: --spout-name QoresencePGM
```

2. Install [Spout2](https://spout.zeal.co/) + OBS Spout plugin. Python side needs `SpoutGL` when you want a real sender (`pip install SpoutGL` on Windows). Without SpoutGL the lobe still starts as a **stub** (health shows `backend: stub:…`) so CI / non-Windows do not crash.
3. OBS: **Spout Capture** source → sender `QoresencePGM` (or your `--spout-name`).
4. OBS: Browser Source **on top** → `http://127.0.0.1:8765/overlay.html` (Lens only).
5. Do **not** add Video Capture Device for `USB3.0 Video`.
6. Audience live to X: OBS Custom RTMP → Live Studio ([X_LIVE_STUDIO.md](X_LIVE_STUDIO.md)).

### Verify

- `/health` → `spout.enabled` true, `published` climbing, `drops` ok under load, `last_frame_seq` moving with FrameHub.
- OBS Spout Capture shows PGM; Lens digits empty unless confirm-licensed.

## Health fields

```json
"spout": {
  "enabled": true,
  "sender_name": "QoresencePGM",
  "backend": "spoutgl",
  "published": 1234,
  "drops": 2,
  "last_frame_seq": 9001,
  "last_clock_ns": 123456789,
  "last_send_age_s": 0.01
}
```

## Future

- **NDI** / **Syphon** (macOS) as sibling pixel glasses — same FrameHub subscribe contract.
- Not a Qoresence encoder. Not Timeline VOD. Not `--x-glass`.

## Related

- [X_LIVE_STUDIO.md](X_LIVE_STUDIO.md) — Live Studio RTMP onboarding
- [X_GLASS.md](X_GLASS.md) — Live 0.9.0 product face + Console coupler
- [OBS_OWNS_CARD.md](OBS_OWNS_CARD.md) — Pattern A vs B
- [RETINA_MONITOR.md](RETINA_MONITOR.md) — FrameHub monitor (also subscribe-only)

---

*HOLD merge until GO MERGE + named SHA in Qorector chat.*
