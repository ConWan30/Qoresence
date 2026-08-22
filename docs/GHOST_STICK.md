# Ghost Stick

Placeholder spec for Grok Build. Not implemented on this branch yet.

DualSense locus sits on the HDMI frame it belongs to. IVC delay (`lag PLL` / `lag_band_ms`) shifts the stick ghost onto FrameHub `frame_seq` / `clock_ns`. If coupling drops, the ghost vanishes. Observation-plane only. No authorship.

Opt-in, default OFF. Not a new capture owner. Subscribe FrameHub + InputRing/IVC only. Do not dual-open the capture card.
