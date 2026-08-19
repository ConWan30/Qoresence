# Controller ↔ video sync

## Pieces

1. **ControllerRuntime** — DualSense / Edge HID edges → bus  
2. **InputRing** — ring of press/release/trigger/stick edges + analog hold  
3. **FrameHub** — `seq` + `clock_ns` per published frame  
4. **IVC** — join window + hold sustain → `coupling_score`  

Enable: `--controller` (starts HID + InputRing pushes + IVC).

## Coupling

Observation only:

```text
window   = [t_video − lag_hi, t_video − lag_lo + lead]
energy   = edge_energy + hold_energy
coupling = 1 - exp(-energy / 2.5)   # clipped [0,1]; EMA at 30 Hz
```

Defaults: `lag_lo=0`, `lag_hi=120`, `lead=24` ms. Held R2/stick still couple.

VCam: `$env:QORESENCE_IVC_LAG_HI_MS = "200"`

## Sidecars

On Foundry export success:

- `clips/<stem>.buttons.json` — button press/release summary (when ring non-empty)
- `clips/<stem>.coupling.json` — latest IVC payload + per-frame `coupling_history`
  keyed by `frame_seq` / `video_clock_ns` + `input_ring_events` in the exact clip window
- `clips/<stem>.otel.json` — trace IDs + Jaeger URLs when `--otel` is enabled

Full: [CONTROLLER_VIDEO_SYNC.md](https://github.com/ConWan30/Qoresence/blob/main/docs/CONTROLLER_VIDEO_SYNC.md) · [OTEL.md](https://github.com/ConWan30/Qoresence/blob/main/docs/OTEL.md)
