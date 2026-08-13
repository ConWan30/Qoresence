# Controller ↔ video sync (observation plane)

Qoresence forks the **physical coupling** stack from QorTroller, not the assertion plane.

| Taken from QorTroller | What Qoresence does with it |
|---|---|
| `hid_report_parser` USB/BT DualSense map | `sync/hid_report.py` — correct IMU offsets |
| L2B IMU-press precursor (5–80 ms) | `sync/imu_ring.py` — stamp `imu_precursor_ms` on edges |
| Event-bind schema (TEMPORAL only) | `sync/event_bind.py` — score/snap ↔ R2/press |
| Cross-channel latency | `sync/lag_estimator.py` — IVC lag band slides |
| Stick↔gyro / optical motion | `sync/optical.py` — COD look-axis quality |

Not taken: PoAC, ZK, IoTeX, TinyML cheat codes, wallets.

## Live path

```
DualSense @ ~1 kHz
  → hid_report.parse (USB 0x01 / BT 0x31)
  → ImuRing (scaled gyro/1000)
  → digital edge + precursor_ms
  → InputRing + EventBinder.hid
Outcome score_changed / first_down / kill
  → EventBinder.visual
IVC
  → lag band from estimator
  → coupling + imu_bodied + last_bind
Ghost Cut / Deck replay
  → pad lights + optional precursor on the sidecar
```

Language stays observation: **coupling / co-occurrence / precursor**. Not authorship, not anti-cheat.
