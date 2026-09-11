# I/O ledger — DualSense return path on the shared clock

Qoresence remains the eyes. QorTroller remains the notary.

A tick may carry three legs. Missing legs stay missing.

| Leg | Source | Required on PS5 |
|---|---|---|
| in / coupling | HDMI + tickets | no — tickets optional |
| `hid_edge` | real pad input report | no — empty is success |
| `out_edge` | real pad **output** report (rumble / trigger / LED) | no — empty is success |

`out_edge` is a console receipt: the title wrote back to the motors. It is not proof of humanity. It is not derived from the picture.

```json
"out_edge": {
  "present": true,
  "kind": "trigger",
  "opcode_hash": "sha256:…",
  "lag_ns": 8000000
}
```

Rules

- No waveform, samples, IMU, or raw haptic bytes.
- `present: true` without a `sha256:` hash is dropped, never filled.
- Optical fields (`hdmi`, `crop`, `score`) cannot mint `out_edge`.
- Commitment includes `out_edge` only when present. Old envelopes still verify.
- Deck export stays observation-only. Seal still waits for `I am the gamer` on QorTroller.
