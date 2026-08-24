# Controller ↔ video sync (observation plane)

Live coupled ticks, DualSense-bodied rules, and `/civif.html` are documented in [CIVIF.md](CIVIF.md). For CIVIF invariants and safety guarantees, see [CIVIF.md](CIVIF.md#civif-invariants).

Qoresence forks the **physical coupling** stack from QorTroller, not the assertion plane.

| Taken from QorTroller | What Qoresence does with it |
|---|---|
| `hid_report_parser` USB/BT DualSense map | `sync/hid_report.py` — correct IMU offsets |
| L2B IMU-press precursor (5–80 ms) | `sync/imu_ring.py` — stamp `imu_precursor_ms` on edges |
| Event-bind schema (TEMPORAL only) | `sync/event_bind.py` — score/snap ↔ R2/press |
| Cross-channel latency | `sync/lag_estimator.py` — IVC lag band slides |
| Stick↔gyro / optical motion | `sync/optical.py` — COD look-axis quality |

Not taken: PoAC, ZK, IoTeX, TinyML cheat codes, wallets.

## Hot-plug

`--play` starts the controller lobe **waiting**. Plug DualSense USB or BT after Deck is up; the loop re-opens HID every 1.5 s. `/health` `state.controller.waiting` is true until the first report, then `connected` flips.

Software stand-in (no pad): `qoresence.sync.dualsense_fixture.feed_bodied_r2(runtime)` drives the same `ingest_report` path as a USB 0x01 stream.

## Live path

```
DualSense @ ~1 kHz
  → hid_report.parse (USB 0x01 / BT 0x31)
  → ImuRing (scaled gyro/1000)
  → digital edge + precursor_ms
  → InputRing edges + throttled analog hold (~60 Hz)
  → EventBinder.hid
Outcome score_changed / first_down / kill
  → EventBinder.visual
IVC @ 30 Hz
  → join [t_video − lag_hi, t_video − lag_lo + lead]
  → edge_energy + hold_energy (fresh analog sustain)
  → play phrase (IDLE/HUDDLE/SNAP/SPRINT/CUT/RELEASE)
  → coupling ticket (licenses heat-speech)
  → coupling + coupling_ema + imu_bodied + last_bind
Glasses
  → GET /health `coupling.imu_bodied`
  → Deck live pad + BODY chip (not just replay)
  → Lens `#body` chip (invisible unless bodied)
  → Monitor HUD `BODY -XXms`
Ghost Cut / Deck replay
  → pad lights + BODY -XXms precursor
  → Foundry ranks chapters by HID-near-score bind
  → receipt.metadata.binds = TEMPORAL (clip-relative)
Ghost Stick (opt-in, default OFF)
  → InputRing analog pose sampled at video_clock_ns − lag_center_ms
  → Theater locus on LIVE only if Same-Seq + paint_reason=ok + coupling
  → gone on idle HID / menu / seq_skew (no last-good pose)
```

Default join is `lag_lo=0`, `lag_hi=120`, `lead=24` (one 60 fps frame of clock skew). Held R2 / stick still score after the onset edge leaves the window. Stale FrameHub stamps (`age_s > 200 ms`) decay coupling. Env: `QORESENCE_IVC_LAG_HI_MS`, `QORESENCE_IVC_LAG_LO_MS`, `QORESENCE_IVC_LEAD_MS`, `QORESENCE_IVC_HZ`.

**Lag PLL (session lock).** IMU-bodied presses vs FrameHub `clock_ns` drive `lag_center_ms` / `lag_jitter_ms` / `pll_lock` on `/health` `coupling`. Frozen video (`age_s` stale) does not walk the PLL. EventBinder samples still only *widen* the envelope — they never shrink it.

**Sub-frame bind.** FrameHub keeps a 16-deep 80×45 luma-energy ring at publish (not a second capture). IVC matches the latest IMU-bodied HID edge to the first luma onset in ±2 frames and stamps `bind_offset_ms` (−16…+16) + `bind_conf`. Observation / co-occurrence only.

Live proof (no extra camera):

```powershell
curl http://127.0.0.1:8765/health
# coupling.imu_bodied = true after a DualSense press that had an IMU jolt
# coupling.last_bind_kind / last_bind_hid after a score/kill/first-down
```

## Clip sidecar: `.coupling.json`

Every clip export writes `clips/<stem>.coupling.json` with a frame-synced
record of the DualSense and IVC state during that replay:

- `coupling` — the latest IVC payload at export time.
- `coupling_history` — every IVC payload whose `video_clock_ns` falls inside
  the clip window, keyed by `frame_seq` and `video_clock_ns`.
- `input_ring_events` — DualSense press / release / trigger / stick events
  whose `clock_ns` falls inside the exact clip window.

When `--otel` is also enabled, the `.otel.json` sidecar links the same clip to
its causal bus trace in Jaeger, so a replay can be correlated with the exact
cascade that produced it.

Language stays observation: **coupling / co-occurrence / precursor**. Not authorship, not anti-cheat.
