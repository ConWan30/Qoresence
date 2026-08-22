# Ghost Stick

DualSense locus sits on the HDMI frame it belongs to. IVC delay (`lag_center_ms` / `lag_band_ms`) shifts the stick ghost onto FrameHub `frame_seq` / `clock_ns`. If coupling drops, the ghost vanishes. Observation-plane only. No authorship.

## Opt-in (default OFF)

```powershell
$env:QORESENCE_GHOST_STICK = "1"
python -m qoresence.cli --play --deck --ghost-stick --streamer-fps 30
```

Not a new capture owner. Subscribes FrameHub stamps + InputRing analog poses + IVC lag only. Does not dual-open the card. Does not interpolate a silent pad. Last-good pose is not painted.

## Gate

Paint only when Dark Theater `paint_reason=ok` **and** Same-Seq (`widget.frame_seq == live.frame_seq`). Veto: `seq_skew`, `not_play`, `no_frame`, `blank`, plane dim, idle HID, coupling below 0.12. Ghost from seq N cannot sit on LIVE N+k.

Theater overlay: `glass/src/components/theater/ghost-stick.tsx` on LIVE. Payload: snapshot `ghost_stick` `{enabled,paint,lx,ly,r2,l2,lag_ms,frame_seq,reason}`.
