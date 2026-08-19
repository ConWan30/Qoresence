# OpenTelemetry (observation plane, default OFF)

Qoresence can export **bus cascade traces** and **capture-health metrics**
via OTLP to a local OpenTelemetry Collector. This is observation of the
event bus and capture pipeline — nothing else. It is not part of any
eligibility, anti-cheat, or verification story, and it never exports event
payloads (no score text, tickets, paths, or keys).

## Guarantees

- **Default OFF.** Same gating as Streamr / A2A. `--play` does not enable it.
- **Local-only.** OTLP endpoint defaults to `http://127.0.0.1:4317`
  (loopback Collector). Nothing leaves the box unless the operator points
  `--otel-endpoint` elsewhere.
- **Non-blocking.** The exporter subscribes to the `RetinaEventBus`, but its
  callback only enqueues into a bounded queue (2048, drop-oldest). A dead or
  stalled Collector can never stall the bus (locked in by
  `tests/test_otel_exporter.py`).
- **No mega-trace.** Traces are short cascades: a bounded group of events
  (≤64) within a ~250 ms `clock_ns` window becomes one small trace tree.
  There is never one open root span for a whole session.
- **Tagged plane.** Every resource and span carries
  `plane=qoresence-observation`.

## Run it

```text
pip install -e ".[otel]"
docker compose --profile otel up -d      # collector (4317/4318) + Jaeger UI (16686), loopback only
python -m qoresence.cli --play ... --otel
```

Env alternative: `QORESENCE_OTEL=1`.

- Jaeger UI: http://127.0.0.1:16686
- Health: `curl http://127.0.0.1:8765/health` → `otel` block
  (`enabled`, `exported`, `dropped`, `last_export_age_s`).

The Collector (see `deploy/otel-collector.yaml`) tail-samples: it keeps
100% of traces containing `router_decision` / `anomaly` / errors, and ~10%
of routine traffic.

## Metrics

| Metric | Kind | Source |
|---|---|---|
| `qoresence_video_age_s` | gauge | `frame_stats` payload |
| `qoresence_video_frames_total` / `qoresence_video_pushes_total` | counter (delta) | `frame_stats` payload |
| `qoresence_fps` | gauge | `frame_stats` payload |
| `qoresence_bus_events_total{lobe,event_type}` | counter | all bus events |
| `qoresence_latency_p95_ms{name}` | gauge | `latency_stats.summary()` |
| `qoresence_otel_dropped` | counter | queue overflow |

## Reading a stuck fan-out

If a lobe ever re-introduces the 2026-08 emit-under-lock class of bug:

- The cascade trace in Jaeger simply **stops mid-tree** (the stuck lobe's
  span never appears / never closes) while sibling lobes keep emitting.
- `/health` shows `otel.dropped` rising if the queue backs up, but
  `video.age_s` stays healthy — proving the exporter is not the blocker.

That combination (trace stops + dropped rising + healthy capture) points at
the bus cascade, not the capture card. Capture `py-spy` stacks as usual.
