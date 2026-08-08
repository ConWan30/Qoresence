# Controller ↔ Video sync (Input–Video Coupler)

**Observation plane only.** Co-occurrence / coupling of DualSense HID edges with streamer frame stamps — **not** legitimacy verification or anti-cheat.

Controller lobe and IVC are **default OFF**. Video path never depends on pad open success.

---

## Architecture

```text
DualSense HID ──ControllerRuntime──► bus (controller_event / trigger_onset / stick_motion)
                    │
                    └── InputRing.push(edge)     # additive, best-effort

StreamerRuntime ──clip_buffer.push_frame
       │
       └── FrameHub.publish(frame, clock_ns)    # same frames; no second capture

Input–Video Coupler (10–20 Hz)
  frame stamp (seq, clock_ns)
  + InputRing.in_window(t_video − lag_hi … t_video − lag_lo)
  → coupling ∈ [0,1], bus EventType.COUPLING_SCORE
  → monitor HUD / Deck snapshot.controller (thin)
```

**Master clock:** `clock_ns()` = `time.monotonic_ns()` (same session for HID and frames).

**Join rule:** time window + optional `frame_seq` — **not** Twitch delay.

---

## Prerequisites

1. **Capture ownership** ([OBS_OWNS_CARD.md](OBS_OWNS_CARD.md)): **recommended Pattern B** — Qoresence owns the physical card (`--streamer-device 0`). Pattern A (OBS → Virtual Cam) is legacy.  
2. Pad must be **PC-visible** (USB cable, or PS Remote Play / similar so Windows sees DualSense HID).  
3. Optional: Retina Monitor ([RETINA_MONITOR.md](RETINA_MONITOR.md)) for local HUD.

Controller is **independent** of who owns the HDMI device. Direct card ownership usually keeps lag in the default band; Virtual Cam (legacy) needs a wider IVC lag band.

---

## Usage

```text
# Play stack + DualSense coupling (default controller OFF without flag)
python -m qoresence.cli --play --deck --controller --streamer-device 0 --streamer-fps 60

# + native monitor HUD (buttons + coupling)
python -m qoresence.cli --play --deck --controller --monitor --streamer-device 0 --streamer-fps 60
```

Wider lag only if using legacy Pattern A VCam:

```text
$env:QORESENCE_IVC_LAG_HI_MS = "200"   # PowerShell; default 120, max 250
```

List HID controllers:

```text
python -c "from qoresence.lobes.controller import list_controllers; print(list_controllers())"
```

If HID open fails, logs a clear hint and **video continues**; InputRing stays empty; coupling ≈ 0.

---

## Lag band

| | Default |
|--|---------|
| lag_lo | 20 ms |
| lag_hi | 120 ms (env up to ~200–250 for VCam) |

IVC scores inputs that fall in `[t_video − lag_hi, t_video − lag_lo]` (inputs slightly before the frame stamp).

**Coupling formula** (simple):  
`coupling = 1 − exp(−input_energy / 2.5)` clipped to [0, 1], where energy is weighted press/trigger/stick edges in the band.

---

## Surfaces

| Surface | Behavior |
|---------|----------|
| Bus `coupling_score` | `frame_seq`, `video_clock_ns`, `buttons`, `input_energy`, `coupling`, `lag_band_ms` |
| Clip sidecar | `clips/<stem>.buttons.json` on successful Foundry export when inputs in window |
| Deck `push_moment` | optional `buttons_summary` when non-empty |
| Deck `/api/situation` | optional `controller: {buttons, coupling, …}` when IVC running |
| Retina Monitor | HUD strip: latest buttons + coupling (if modules importable) |
| Moment scorer | slight clip_gate boost when high coupling **and** clutch context; moments still fire without controller |

---

## Out of scope

- Second `VideoCapture` for “sync”  
- Twitch-delay alignment  
- Truth-plane / anti-cheat claims  
- Full 1 kHz state dumps to JSONL (edges + decimated snapshots only)

---

## Related

- [OBS_OWNS_CARD.md](OBS_OWNS_CARD.md) — capture ownership; controller independent of HDMI owner  
- [RETINA_MONITOR.md](RETINA_MONITOR.md) — FrameHub consumer glass  
