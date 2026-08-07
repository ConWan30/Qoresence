# Controller ↔ video sync

## Pieces

1. **ControllerRuntime** — DualSense / Edge HID edges → bus  
2. **InputRing** — ring of press/release/trigger/stick edges  
3. **FrameHub** — `seq` + `clock_ns` per published frame  
4. **IVC** — lag-band join → `coupling_score`  

Enable: `--controller` (starts HID + InputRing pushes + IVC).

## Coupling

Observation only:

```text
coupling = 1 - exp(-input_energy / 2.5)   # clipped [0,1]
```

Inputs in `[t_video - lag_hi, t_video - lag_lo]` (defaults 20–120 ms).

VCam: `$env:QORESENCE_IVC_LAG_HI_MS = "200"`

## Sidecars

On Foundry export success → `clips/<stem>.buttons.json` when ring non-empty.

Full: [CONTROLLER_VIDEO_SYNC.md](https://github.com/ConWan30/Qoresence/blob/main/docs/CONTROLLER_VIDEO_SYNC.md)
